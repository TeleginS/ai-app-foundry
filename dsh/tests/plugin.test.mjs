import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import { join } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

import { apply, inject, name } from '../index.mjs'

const REPO_ROOT = fileURLToPath(new URL('../../', import.meta.url))
const SKILLS_ROOT = join(REPO_ROOT, 'skills')
const FRONTMATTER = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/u

/**
 * Mount the plugin against a minimal Cordis context and collect its provider.
 * @returns {{ providers: object[], warnings: string[] }} mounted providers and logged warnings.
 */
function mountPlugin() {
  const warnings = []
  const providers = []
  const ctx = {
    logger: { warn: (message) => warnings.push(String(message)) },
    skills: {
      registerProvider(create) {
        providers.push(create({ signal: new AbortController().signal, invalidate() {} }))
        return () => {}
      },
    },
  }
  apply(ctx)
  return { providers, warnings }
}

test('exports a Cordis plugin that requires the skill registry', () => {
  assert.equal(name, 'ai-app-foundry')
  assert.deepEqual(inject, ['skills'])
})

test('registers exactly one bundled skill provider', () => {
  const { providers, warnings } = mountPlugin()
  assert.equal(providers.length, 1)
  assert.equal(providers[0].name, 'ai-app-foundry')
  assert.deepEqual(warnings, [])
})

test('lists every skill directory as a bundled candidate', async () => {
  const { providers } = mountPlugin()
  const entries = await readdir(SKILLS_ROOT, { withFileTypes: true })
  const expected = entries.filter((entry) => entry.isDirectory()).map((entry) => entry.name).sort()

  const candidates = await providers[0].list({})
  assert.deepEqual(candidates.map((candidate) => candidate.name).sort(), expected)

  const candidate = candidates.find((entry) => entry.name === 'publish-app-release')
  assert.ok(candidate, 'publish-app-release must be listed')
  assert.equal(candidate.source, 'bundled')
  assert.equal(candidate.rank, 600)
  assert.equal(candidate.provider, 'ai-app-foundry')
  assert.deepEqual(candidate.invocation, { modelInvocable: true, userInvocable: true })
  assert.equal(candidate.resourceBase.kind, 'directory')
  assert.equal(candidate.resourceBase.path, join(SKILLS_ROOT, 'publish-app-release'))
  assert.equal(candidate.path, join(SKILLS_ROOT, 'publish-app-release', 'SKILL.md'))
  assert.equal(candidate.locator, candidate.path)

  const raw = await readFile(candidate.path, 'utf8')
  const frontmatter = FRONTMATTER.exec(raw)
  assert.ok(frontmatter, 'SKILL.md must have YAML frontmatter')
  const description = /^description:[ \t]*(.+)$/mu.exec(frontmatter[1])
  assert.ok(description, 'SKILL.md must declare a description')
  assert.equal(candidate.description, description[1].trim())
})

test('loads the instruction body without frontmatter and keeps the summary', async () => {
  const { providers } = mountPlugin()
  const [candidate] = (await providers[0].list({})).filter((entry) => entry.name === 'publish-app-release')
  assert.ok(candidate)

  const loaded = await providers[0].get(candidate, {})
  assert.equal(loaded.name, candidate.name)
  assert.equal(loaded.description, candidate.description)
  assert.equal(loaded.source, 'bundled')
  assert.equal(loaded.provider, 'ai-app-foundry')
  assert.equal(loaded.resourceBase.path, candidate.resourceBase.path)
  assert.equal(loaded.path, candidate.path)
  assert.equal(loaded.rank, undefined)
  assert.equal(loaded.locator, undefined)

  const raw = await readFile(candidate.path, 'utf8')
  const expectedBody = raw.replace(FRONTMATTER, '').trim()
  assert.equal(loaded.content, expectedBody)
  assert.ok(!loaded.content.startsWith('---'))
  assert.ok(loaded.content.startsWith('# Publish iOS App Release'))
})
