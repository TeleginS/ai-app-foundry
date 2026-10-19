/**
 * DeepSeek Harness plugin bundle for AI App Foundry.
 *
 * DSH plugins that contribute instructions rather than tools register a skill
 * provider on `ctx.skills`; the shipped `dsh-skill-badge` and `dsh-skill-office`
 * packages are the reference implementations. This bundle does the same for
 * every skill directory under the package's `skills/` root, so Codex, Claude
 * Code, and DSH all serve one copy of each `SKILL.md`.
 */

import { statSync } from 'node:fs'
import { readFile, readdir, stat } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

/** Cordis plugin name. */
export const name = 'ai-app-foundry'

/** Service required by the bundled skill provider. */
export const inject = ['skills']

/** Provider label carried by every skill this bundle serves. */
const PROVIDER_NAME = 'ai-app-foundry'

/**
 * Standard rank for packaged skill providers and local bundled roots, exported
 * by `@deepseek-ai/dsh-skill` as `BUNDLED_SKILL_RANK`. It is repeated here
 * because a third-party bundle cannot rely on resolving host packages from a
 * pnpm profile.
 */
const BUNDLED_SKILL_RANK = 600

/** Absolute root of the bundled skill directories. */
const SKILLS_ROOT = fileURLToPath(new URL('../skills/', import.meta.url))

const SKILL_FILE = 'SKILL.md'
const SKILL_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/u
const FRONTMATTER = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/u
const TRUE_VALUES = new Set(['true', 'yes', 'on', '1'])
const FALSE_VALUES = new Set(['false', 'no', 'off', '0'])

/**
 * Read one YAML scalar from a skill frontmatter value.
 * @param {string} raw - scalar text to the right of the key.
 * @returns {string} the decoded scalar.
 */
function parseScalar(raw) {
  const value = raw.trim()
  if (value === '') return ''
  if (value.startsWith('"')) {
    try {
      const decoded = JSON.parse(value)
      if (typeof decoded === 'string') return decoded
    } catch {
      // Fall through to the explicit error below.
    }
    throw new Error(`invalid double-quoted scalar: ${value}`)
  }
  if (value.startsWith("'") && value.length >= 2 && value.endsWith("'")) {
    return value.slice(1, -1).replaceAll("''", "'")
  }
  return value
}

/**
 * Parse the flat YAML frontmatter of one skill file plus the Markdown body.
 *
 * Skills in this repository use flat `key: value` frontmatter (with optional
 * literal/folded block scalars); nested YAML is rejected because DSH skill
 * frontmatter has no nested fields.
 * @param {string} raw - full file contents.
 * @param {string} filePath - path used in error messages.
 * @returns {{ fields: Record<string, string>, body: string }} parsed frontmatter and instruction body.
 */
function parseFrontmatter(raw, filePath) {
  const match = FRONTMATTER.exec(raw)
  if (match === null) throw new Error(`${filePath}: expected YAML frontmatter delimited by "---"`)
  const fields = {}
  const lines = match[1].split(/\r?\n/)
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]
    if (line.trim() === '' || line.trimStart().startsWith('#')) continue
    if (/^\s/u.test(line)) {
      throw new Error(`${filePath}: indented frontmatter is only supported inside a block scalar: ${JSON.stringify(line)}`)
    }
    const entry = /^([A-Za-z0-9_-]+):[ \t]*(.*)$/u.exec(line)
    if (entry === null) throw new Error(`${filePath}: unsupported frontmatter line: ${JSON.stringify(line)}`)
    const [, key, rawValue] = entry
    const marker = /^([|>])[+-]?$/u.exec(rawValue.trim())
    if (marker === null) {
      fields[key] = parseScalar(rawValue)
      continue
    }
    const block = []
    while (index + 1 < lines.length && (lines[index + 1].trim() === '' || /^\s/u.test(lines[index + 1]))) {
      block.push(lines[index + 1])
      index += 1
    }
    if (block.length === 0) {
      fields[key] = ''
      continue
    }
    const nonEmpty = block.filter((blockLine) => blockLine.trim() !== '')
    if (nonEmpty.length === 0) {
      fields[key] = ''
      continue
    }
    const indent = Math.min(...nonEmpty.map((blockLine) => /^[ \t]*/u.exec(blockLine)[0].length))
    const normalized = block.map((blockLine) => blockLine.slice(indent))
    fields[key] = marker[1] === '|'
      ? normalized.join('\n')
      : normalized.join('\n').split(/\n[ \t]*\n/u).map((paragraph) => paragraph.split('\n').map((part) => part.trim()).join(' ')).join('\n').trim()
  }
  return { fields, body: raw.slice(match[0].length).trim() }
}

/**
 * Decode a DSH invocation-policy boolean.
 * @param {string} value - raw frontmatter value.
 * @param {string} key - frontmatter key, used in error messages.
 * @param {string} filePath - skill file path, used in error messages.
 * @returns {boolean} the decoded boolean.
 */
function parseBoolean(value, key, filePath) {
  const normalized = String(value).trim().toLowerCase()
  if (TRUE_VALUES.has(normalized)) return true
  if (FALSE_VALUES.has(normalized)) return false
  throw new Error(`${filePath}: "${key}" must be a boolean, got ${JSON.stringify(value)}`)
}

/**
 * Build one skill candidate from a directory bundle.
 * @param {string} directoryName - directory under `skills/`.
 * @returns {Promise<object>} the provider candidate for the skill.
 */
async function readCandidate(directoryName) {
  const directory = join(SKILLS_ROOT, directoryName)
  const path = join(directory, SKILL_FILE)
  const info = await stat(path)
  if (!info.isFile()) throw new Error(`${path} is not a regular file`)
  const raw = await readFile(path, 'utf8')
  const { fields } = parseFrontmatter(raw, path)
  const skillName = fields.name
  if (typeof skillName !== 'string' || !SKILL_NAME.test(skillName)) {
    throw new Error(`${path}: "name" is missing or not kebab-case`)
  }
  const description = fields.description
  if (typeof description !== 'string' || description.trim() === '') {
    throw new Error(`${path}: "description" is required`)
  }
  const invocation = { modelInvocable: true, userInvocable: true }
  if (fields['disable-model-invocation'] !== undefined) {
    invocation.modelInvocable = !parseBoolean(fields['disable-model-invocation'], 'disable-model-invocation', path)
  }
  if (fields['user-invocable'] !== undefined) {
    invocation.userInvocable = parseBoolean(fields['user-invocable'], 'user-invocable', path)
  }
  const candidate = {
    name: skillName,
    description: description.trim(),
    invocation,
    provider: PROVIDER_NAME,
    source: 'bundled',
    rank: BUNDLED_SKILL_RANK,
    path,
    resourceBase: { kind: 'directory', path: directory },
    locator: path,
  }
  if (typeof fields.whenToUse === 'string' && fields.whenToUse.trim() !== '') {
    candidate.whenToUse = fields.whenToUse.trim()
  }
  return candidate
}

/**
 * Create the immutable bundled provider served to the DSH registry.
 * @param {object} ctx - Cordis context carrying the skill registry.
 * @returns {object} the `ctx.skills` provider.
 */
function createProvider(ctx) {
  return {
    name: PROVIDER_NAME,
    async list(options) {
      options?.signal?.throwIfAborted?.()
      const entries = await readdir(SKILLS_ROOT, { withFileTypes: true })
      const candidates = []
      for (const entry of entries) {
        if (!entry.isDirectory()) continue
        try {
          candidates.push(await readCandidate(entry.name))
        } catch (error) {
          // One malformed skill must not remove the readable ones from the catalog.
          const reason = error instanceof Error ? error.message : String(error)
          ctx.logger.warn(`ai-app-foundry: skipping skill "${entry.name}": ${reason}`)
        }
      }
      options?.signal?.throwIfAborted?.()
      return candidates
    },
    async get(candidate, options) {
      const { rank: _rank, locator, ...summary } = candidate
      const raw = await readFile(locator, { encoding: 'utf8', signal: options?.signal })
      const { body } = parseFrontmatter(raw, locator)
      return { ...summary, content: body }
    },
  }
}

/**
 * Register the bundled skill provider.
 * @param {object} ctx - Cordis context carrying the skill registry.
 * @returns {void}
 */
export function apply(ctx) {
  let isDirectory = false
  try {
    isDirectory = statSync(SKILLS_ROOT).isDirectory()
  } catch {
    isDirectory = false
  }
  if (!isDirectory) throw new Error(`ai-app-foundry: bundled skills directory is missing: ${SKILLS_ROOT}`)
  ctx.skills.registerProvider(() => createProvider(ctx))
}
