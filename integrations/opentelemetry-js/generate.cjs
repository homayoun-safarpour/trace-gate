/* Original synthetic fixture generator. No HTTP exporter or collector is used. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { createRequire } = require('node:module');
const [runtimeArgument, outputArgument] = process.argv.slice(2);
if (!runtimeArgument || !outputArgument || process.argv.length !== 4) {
  throw new Error('Usage: node generate.cjs RUNTIME_DIRECTORY OUTPUT_DIRECTORY');
}
const runtime = path.resolve(runtimeArgument);
const output = path.resolve(outputArgument);
const req = createRequire(path.join(runtime, 'package.json'));
const hash = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
const expected = {
  '@opentelemetry/api': '1.9.1',
  '@opentelemetry/sdk-trace-base': '2.12.1',
  '@opentelemetry/sdk-trace': '2.12.1',
  '@opentelemetry/resources': '2.12.1',
  '@opentelemetry/otlp-transformer': '0.223.1',
};
const lockBytes = fs.readFileSync(path.join(runtime, 'package-lock.json'));
const lock = JSON.parse(lockBytes);
const packages = {};
for (const [name, version] of Object.entries(expected)) {
  const packageRoot = fs.realpathSync(path.join(runtime, 'node_modules', name));
  const metadata = JSON.parse(fs.readFileSync(path.join(packageRoot, 'package.json')));
  const pinned = lock.packages['node_modules/' + name];
  const entry = fs.realpathSync(req.resolve(name));
  if (metadata.name !== name || metadata.version !== version || pinned?.version !== version
      || !entry.startsWith(packageRoot + path.sep)) {
    throw new Error('Installed package does not match expected locked runtime: ' + name);
  }
  packages[name] = {
    version, license: metadata.license, resolved: pinned.resolved, integrity: pinned.integrity,
    entry_sha256: hash(fs.readFileSync(entry)),
  };
}
const { BasicTracerProvider, SimpleSpanProcessor, InMemorySpanExporter, AlwaysOnSampler }
  = req('@opentelemetry/sdk-trace-base');
const { ROOT_CONTEXT, trace, SpanStatusCode } = req('@opentelemetry/api');
const { resourceFromAttributes } = req('@opentelemetry/resources');
const { JsonTraceSerializer } = req('@opentelemetry/otlp-transformer');
const scenarios = ['good', 'forbidden-generated', 'repeated-name', 'events',
  'dropped-attributes', 'missing-call-id'];
const time = (offset) => [1700000000, offset];
async function generate(scenario) {
  let nextId = 0;
  const exporter = new InMemorySpanExporter();
  const provider = new BasicTracerProvider({
    sampler: new AlwaysOnSampler(),
    resource: resourceFromAttributes({ 'service.name': 'trace-gate-synthetic',
      'synthetic.secret': 'SYNTHETIC_PAYLOAD_RESOURCE' }),
    idGenerator: { generateTraceId: () => '1'.repeat(32),
      generateSpanId: () => (++nextId).toString(16).padStart(16, '0') },
    spanLimits: { attributeCountLimit: 16 },
    spanProcessors: [new SimpleSpanProcessor(exporter)],
  });
  try {
    const tracer = provider.getTracer('trace-gate-offline-fixture', '1.0');
    const root = tracer.startSpan('SYNTHETIC_PAYLOAD_ROOT', {
      startTime: time(0), attributes: { 'openinference.span.kind': 'AGENT' },
    });
    const context = trace.setSpan(ROOT_CONTEXT, root);
    const attrs = {
      'openinference.span.kind': 'LLM',
      'llm.output_messages.0.message.role': 'assistant',
      'llm.output_messages.0.message.tool_calls.0.tool_call.id': 'call-one',
      'llm.output_messages.0.message.tool_calls.0.tool_call.function.name': 'search',
      'llm.output_messages.0.message.tool_calls.0.tool_call.function.arguments': 'SYNTHETIC_PAYLOAD_ARGUMENTS',
      'input.value': 'SYNTHETIC_PAYLOAD_INPUT',
      'output.value': '__REDACTED__',
    };
    if (['forbidden-generated', 'repeated-name'].includes(scenario)) {
      attrs['llm.output_messages.0.message.tool_calls.1.tool_call.id'] = 'call-two';
      attrs['llm.output_messages.0.message.tool_calls.1.tool_call.function.name'] =
        scenario === 'forbidden-generated' ? 'delete_database' : 'search';
    }
    const llm = tracer.startSpan('SYNTHETIC_PAYLOAD_LLM', {
      startTime: time(10), attributes: attrs,
    }, context);
    llm.end(time(100));
    const toolAttrs = { 'openinference.span.kind': 'TOOL', 'tool.name': 'search',
      'output.value': 'SYNTHETIC_PAYLOAD_OUTPUT' };
    if (scenario !== 'missing-call-id') toolAttrs['tool.id'] = 'call-one';
    const tool = tracer.startSpan('SYNTHETIC_PAYLOAD_TOOL', {
      startTime: time(110), attributes: toolAttrs,
    }, context);
    tool.setStatus({ code: SpanStatusCode.ERROR, message: 'SYNTHETIC_PAYLOAD_STATUS' });
    if (scenario === 'events') tool.addEvent('SYNTHETIC_PAYLOAD_EVENT', {}, time(150));
    if (scenario === 'dropped-attributes') {
      for (let i = 0; i < 32; i++) tool.setAttribute('synthetic.extra.' + i, i);
    }
    tool.end(time(200));
    root.end(time(300));
    await provider.forceFlush();
    const spans = exporter.getFinishedSpans();
    if (spans.length !== 3) throw new Error('Expected three real SDK spans');
    return JsonTraceSerializer.serializeRequest(spans);
  } finally {
    await provider.shutdown();
  }
}
(async () => {
  fs.mkdirSync(output, { recursive: true });
  const fixtureHashes = {};
  for (const scenario of scenarios) {
    const bytes = await generate(scenario);
    fs.writeFileSync(path.join(output, scenario + '.json'), bytes);
    fixtureHashes[scenario + '.json'] = hash(bytes);
  }
  fs.writeFileSync(path.join(output, 'provenance.json'), JSON.stringify({
    generator: 'original synthetic spans through real SDK and JsonTraceSerializer',
    node: process.version, packages, runtime_lock_sha256: hash(lockBytes),
    generator_sha256: hash(fs.readFileSync(__filename)), fixtures: fixtureHashes,
    network_exporter: false, model_calls: 0,
  }, null, 2) + '\n');
  console.log('Generated six offline fixtures using the pinned installed OpenTelemetry runtime.');
})().catch((error) => { console.error(error.message); process.exitCode = 1; });
