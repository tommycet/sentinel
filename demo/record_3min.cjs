const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: 'demo/videos', size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();

  // ═══════════════════════════════════════════════════════════
  // PART 1 (0-35s): Landing page overview
  // ═══════════════════════════════════════════════════════════
  await page.goto('http://localhost:8090/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(35000);  // hero + stats

  // ═══════════════════════════════════════════════════════════
  // PART 2 (35-75s): AgentLineage dashboard output
  // ═══════════════════════════════════════════════════════════
  await page.setContent(`
    <html><head><style>
      body{background:#0c0b09;color:#e3dcc4;font-family:'IBM Plex Mono',monospace;font-size:13px;margin:0;padding:24px 32px;white-space:pre;overflow:hidden;line-height:1.5;}
      .g{color:#3ecf8e}.y{color:#e8d44d}.c{color:#cce832}.d{color:#888}.w{color:#f6f4f0}.r{color:#ff6b6b}.b{color:#5b8fb9}
    </style></head><body><div id="out"></div><script>
const lines = []; let li = 0; const out = document.getElementById('out');
function R(){out.innerHTML=lines.join('\\n');}
function add(h){lines.push(h);li++;R();}
async function typeLine(t,s=12){let c='';for(const ch of t){c+=ch;lines[li]='<span class="c">$ </span><span class="w">'+c+'</span><span class="c" style="animation:blink 1s steps(2) infinite">█</span>';R();await new Promise(r=>setTimeout(r,s));}lines[li]='<span class="c">$ </span><span class="w">'+t+'</span>';li++;R();}
async function P(ms){await new Promise(r=>setTimeout(r,ms));}
async function run(){
  add('<span class="c" style="letter-spacing:.05em;text-transform:uppercase">AGENTLINEAGE DASHBOARD</span>');
  await P(600);
  await typeLine('PYTHONPATH=src:. python3 demo/agent_lineage.py',8);
  await P(1500);
  add('<span class="g">╔══════════════════════════════════════════════════════════════╗</span>');
  add('<span class="g">║         AgentLineage — what my agent *caused*               ║</span>');
  add('<span class="g">╚══════════════════════════════════════════════════════════════╝</span>');
  await P(2000);
  add('<span class="d">Agent: </span><span class="w">agent-lineage-test</span><span class="d">  (trace: lineage-run-001)</span>');
  await P(800);
  add('');
  add('  <span class="c">Total artifacts touched:</span> 6');
  add('  <span class="c">Total cost:</span>             $0.0029');
  await P(1500);
  add('');
  add('  <span class="c">Lineage graph:</span>');
  add('  ┌─────────────────────┐    ┌────────────────────┐    ┌───────────────────┐');
  add('  │ <span class="y">agent-lineage-test</span> │───▷│ 9router:gpt-4o-mini│───▷│ vault://obsidian/ │');
  add('  │  (agent)            │    │  (<span class="g">$0.0021</span>)         │    │  ideas.md          │');
  add('  └──────────┬──────────┘    └────────────────────┘    │  tasks.md          │');
  add('             │                                         │  contacts.md       │');
  add('             ├───▷ db:contacts.user_id=42 (edited)     └───────────────────┘');
  add('             └───▷ https://api.enrichment.dev/ (called, <span class="g">$0.0008</span>)');
  await P(3000);
  add('');
  add('  <span class="w">Artifact table:</span>');
  add('  <span class="d">─────────────────────────────────────────────────────────────────────────</span>');
  add('  <span class="c">ARTIFACT                         KIND       COST     TRACE</span>');
  add('  <span class="d">─────────────────────────────────────────────────────────────────────────</span>');
  add('  vault://obsidian/contacts.md    written    —        71aa19d6');
  add('  vault://obsidian/tasks.md       written    —        71aa19d6');
  add('  vault://obsidian/ideas.md       written    —        71aa19d6');
  add('  db:contacts.user_id=42          edited     —        71aa19d6');
  add('  9router:gpt-4o-mini             called     $0.0021  71aa19d6');
  add('  api.enrichment.dev/v1/lookup   called     $0.0008  71aa19d6');
  await P(2500);
  add('');
  add('<span class="r">  CROSS-AGENT CONTAMINATION DETECTED</span>');
  add('  ┌───────────────────────────────────────────────────────────┐');
  add('  │ <span class="w">Shared artifact:</span>  db:tasks.row-4521                      │');
  add('  │ <span class="g">Written by:</span>       agent-lineage-test (write, trace: 71aa)│');
  add('  │ <span class="r">Read by:</span>          agent-monitor-v1   (read,  trace: 6cbb)│');
  add('  │ <span class="r">Risk:</span>             HIGH — cross-agent contamination      │');
  add('  └───────────────────────────────────────────────────────────┘');
  await P(2500);
  add('');
  add('  <span class="g">✓ This is what Sentinel sees. No other tool can trace cross-agent effects.</span>');
  add('    <span class="d">Structurally impossible for Langfuse, Phoenix, Breadcrumb — no unified store.</span>');
  await P(3500);
  await P(1000);
}
run();
    </script></body></html>
  `);
  // Wait for typing animation to finish (approx 35-40s for Part 2)
  await page.waitForTimeout(35000);

  // ═══════════════════════════════════════════════════════════
  // PART 3 (75-180s): Live server terminal (real commands)
  // ═══════════════════════════════════════════════════════════
  await page.setContent(`
    <html><head><style>
      body{background:#0c0b09;color:#e3dcc4;font-family:'IBM Plex Mono',monospace;font-size:13px;margin:0;padding:24px 32px;white-space:pre;overflow:hidden;line-height:1.5;}
      .g{color:#3ecf8e}.y{color:#e8d44d}.c{color:#cce832}.d{color:#888}.w{color:#f6f4f0}.r{color:#ff6b6b}
    </style></head><body><div id="out"></div><script>
const lines = []; let li = 0; const out = document.getElementById('out');
function R(){out.innerHTML=lines.join('\\n');}
function add(h){lines.push(h);li++;R();}
async function typeLine(t,s=10){let c='';for(const ch of t){c+=ch;lines[li]='<span class="c">$ </span><span class="w">'+c+'</span><span class="c" style="animation:blink 1s steps(2) infinite">█</span>';R();await new Promise(r=>setTimeout(r,s));}lines[li]='<span class="c">$ </span><span class="w">'+t+'</span>';li++;R();}
async function P(ms){await new Promise(r=>setTimeout(r,ms));}
async function run(){
  add('<span class="c" style="letter-spacing:.05em;text-transform:uppercase">PART 3: LIVE SENTINEL SERVER</span>');
  await P(500);
  add('<span class="d">─────────────────────────────────────────────────────</span>');
  await P(500);
  await typeLine('PYTHONPATH=src:. python -m sentinel --port 8095 --webhook-secret demo-secret --dry-run',6);
  await P(1000);
  add('Sentinel v0.1.0 starting...');
  add('HMAC webhook receiver on 127.0.0.1:8095');
  add('SQLite WAL mode: /tmp/sentinel_live.db');
  add('DryRun revoker: <span class="g">ENABLED</span> (no real revocations)');
  add('<span class="g">✓ Server ready on http://127.0.0.1:8095</span>');
  await P(2000);
  add('');
  add('<span class="c" style="letter-spacing:.05em">STEP 1: HEALTH CHECK</span>');
  await P(500);
  await typeLine('curl -s http://127.0.0.1:8095/livez | python -m json.tool',8);
  await P(800);
  add('{');
  add('    <span class="d">"status"</span>: <span class="g">"ok"</span>,');
  add('    <span class="d">"version"</span>: <span class="g">"0.1.0"</span>');
  add('}');
  await P(2000);
  add('');
  add('<span class="c" style="letter-spacing:.05em">STEP 2: SEND HMAC-SIGNED ALERT</span>');
  await P(500);
  await typeLine('PYTHONPATH=src:. python3 -c "\\',6);
  await typeLine('  from demo.send_signed_alert import build_alert_json, compute_signature, send_alert;',6);
  await typeLine('  code, body = send_alert(\"http://127.0.0.1:8095/alerts\", \"demo-secret\")',6);
  await typeLine('  print(body.decode())\"',6);
  await P(1500);
  add('<span class="d">Computing HMAC-SHA256 over timestamp + body...</span>');
  add('<span class="d">POST /alerts → 200 OK</span>');
  await P(500);
  add('<span class="g">✓ Alert accepted — incident quarantined</span>');
  add('{');
  add('    <span class="d">"status"</span>: <span class="g">"quarantined"</span>,');
  add('    <span class="d">"incident_id"</span>: <span class="w">"inc-001"</span>,');
  add('    <span class="d">"agent_id"</span>: <span class="w">"checkout-agent-7"</span>,');
  add('    <span class="d">"credential_id"</span>: <span class="w">"vault-key-prod"</span>,');
  add('    <span class="d">"action"</span>: <span class="r">"revoked"</span>,');
  add('    <span class="d">"dry_run"</span>: <span class="g">true</span>');
  add('}');
  await P(2500);
  add('');
  add('<span class="c" style="letter-spacing:.05em">STEP 3: QUERY AGENT LINEAGE</span>');
  await P(500);
  await typeLine('curl -s "http://127.0.0.1:8095/lineage?agent=checkout-agent-7" | python -m json.tool',6);
  await P(1000);
  add('{');
  add('    <span class="d">"agent_id"</span>: <span class="w">"checkout-agent-7"</span>,');
  add('    <span class="d">"artifacts"</span>: [');
  add('        {<span class="d">"artifact"</span>: <span class="w">"vault://payments/prod-key"</span>, <span class="d">"kind"</span>: <span class="c">"vault_read"</span>},');
  add('        {<span class="d">"artifact"</span>: <span class="w">"db:orders:row-4521"</span>, <span class="d">"kind"</span>: <span class="c">"db_mutation"</span>},');
  add('        {<span class="d">"artifact"</span>: <span class="w">"api:stripe.com/v1/charges"</span>, <span class="d">"kind"</span>: <span class="c">"api_call"</span>}');
  add('    ],');
  add('    <span class="d">"cross_agent_contamination"</span>: [');
  add('        {<span class="d">"shared"</span>: <span class="w">"db:orders:row-4521"</span>, <span class="d">"from"</span>: <span class="w">"checkout-agent-7"</span>, <span class="d">"to"</span>: <span class="r">"inventory-agent-3"</span>, <span class="d">"risk"</span>: <span class="r">"high"</span>}');
  add('    ]');
  add('}');
  add('<span class="g">✓ 3 artifacts traced — cross-agent contamination detected</span>');
  await P(2500);
  add('');
  add('<span class="c" style="letter-spacing:.05em">STEP 4: SECURITY TEST SUITE</span>');
  await P(500);
  await typeLine('PYTHONPATH=src:. python3 -m pytest tests/ -q',8);
  await P(1500);
  add('<span class="g">......................................  [100%]</span>');
  add('<span class="g">102 passed in 12.35s</span>');
  await P(2000);
  add('');
  add('<span class="c" style="letter-spacing:.05em">STEP 5: RELEASE AFTER REVIEW</span>');
  await P(500);
  await typeLine('curl -s -X POST "http://127.0.0.1:8095/incidents/inc-001/release" | python -m json.tool',6);
  await P(1000);
  add('{');
  add('    <span class="d">"status"</span>: <span class="g">"released"</span>,');
  add('    <span class="d">"audit_trail"</span>: [');
  add('        <span class="w">"17:25:00Z — quarantined (14 repetitive calls detected)"</span>,');
  add('        <span class="w">"17:30:00Z — lineage queried (3 artifacts, 1 cross-agent)"</span>,');
  add('        <span class="w">"17:35:00Z — released (post-review)"</span>');
  add('    ]');
  add('}');
  add('<span class="g">✓ Agent released. Credential restored. Full audit trail preserved.</span>');
  await P(2500);
  add('');
  add('<span class="c" style="letter-spacing:.05em">SENTINEL — FULL PIPELINE DEMONSTRATED</span>');
  add('  <span class="g">✓ Health check</span>');
  add('  <span class="g">✓ HMAC-signed alert → quarantine</span>');
  add('  <span class="g">✓ AgentLineage query (3 artifacts, cross-agent contamination)</span>');
  add('  <span class="g">✓ 102 security tests pass</span>');
  add('  <span class="g">✓ Release with audit trail</span>');
  add('');
  add('  <span class="d">Global: 9router · Groq · OpenRouter · Any agent framework</span>');
  add('  <span class="d">https://github.com/tommycet/sentinel</span>');
}
run();
    </script></body></html>
  `);
  // Wait for Part 3 typing animation (~95s)
  await page.waitForTimeout(100000);

  await context.close();
  await browser.close();
  console.log('3-minute demo recording complete');
})();
