// Compare two production builds against the same isolated Large fixture over HTTP.
// Usage: node benchmark_reference_pickers.cjs READY_JSON FIXTURE_JSON BEFORE_DIST AFTER_DIST OUTPUT
const fs = require('node:fs')
const path = require('node:path')
const assert = require('node:assert/strict')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')

async function main() {
  const [readyFile, fixtureFile, before, after, output] = process.argv.slice(2)
  const { baseUrl } = JSON.parse(fs.readFileSync(readyFile))
  const fixture = JSON.parse(fs.readFileSync(fixtureFile))
  assert.equal(new URL(baseUrl).hostname, '127.0.0.1')
  assert.deepEqual(fixture.counts, { projects: 100, cases: 20000, pipelines: 0 })
  const browser = await chromium.launch({ headless: true, chromiumSandbox: true, executablePath: process.env.BROWSER_BIN })
  const samples = []
  try {
    for (let trial = 0; trial <= 5; trial++) {
      for (const screen of ['dashboard', 'pipeline']) {
        for (const phase of (trial % 2 ? ['after', 'before'] : ['before', 'after'])) {
          const dist = phase === 'before' ? before : after
          const page = await browser.newPage()
          try {
            const endpoint = screen === 'dashboard' ? '/dashboard' : '/pipelines/editor?project=load-test%2Fproject-000'
            await page.route(baseUrl + endpoint.split('?')[0] + '*', route => route.fulfill({ path: path.join(dist, 'index.html'), contentType: 'text/html' }))
            await page.route(baseUrl + '/assets/**', route => route.fulfill({ path: path.join(dist, 'assets', path.basename(new URL(route.request().url()).pathname)) }))
            const requests = []
            page.on('response', response => {
              const url = new URL(response.url())
              if (url.origin === baseUrl && ['/api/projects', '/api/cases', '/api/pipelines'].includes(url.pathname)) requests.push(response)
            })
            const prefix = screen === 'dashboard' ? 'load-test/project-' : 'load-test/health/'
            await page.addInitScript(prefix => {
              const observer = new MutationObserver(() => {
                for (const select of document.querySelectorAll('select')) {
                  const count = [...select.options].filter(o => o.value.startsWith(prefix)).length
                  if (count > 1 && !select.disabled) {
                    window.selectorSample = { options: count, readyMs: performance.now() }
                    observer.disconnect()
                    break
                  }
                }
              })
              observer.observe(document, { subtree: true, childList: true, attributes: true })
            }, prefix)
            await page.goto(baseUrl + endpoint)
            await page.waitForFunction(() => !!window.selectorSample)
            await page.waitForLoadState('networkidle')
            const measure = await page.evaluate(() => window.selectorSample)
            assert.equal(measure.options, phase === 'after' ? 20 : screen === 'dashboard' ? 100 : 200)
            const http = await Promise.all(requests.map(async response => {
              assert.equal(response.status(), 200)
              const bytes = await response.body()
              const url = new URL(response.url())
              const ms = response.request().timing().responseEnd
              assert(ms >= 0)
              return { query: url.pathname + url.search, refs: JSON.parse(bytes).items.length, bytes: bytes.length, ms }
            }))
            assert.equal(http.length, phase === 'after' ? 1 : 3)
            samples.push({ trial, phase, screen, ...measure, http })
          } finally { await page.close() }
        }
      }
    }
    fs.writeFileSync(output, JSON.stringify({ fixture: fixture.fixtureSha256, counts: fixture.counts, seed: fixture.seed,
      browser: browser.version(), samples }, null, 2) + '\n')
  } finally { await browser.close() }
}
main().catch(error => { console.error(error.message); process.exitCode = 1 })
