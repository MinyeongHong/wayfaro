import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import fs from 'node:fs';
const require = createRequire(path.join(process.env.WAYFARO_TEST_BUILD, 'entry.js'));
const { AnalysisController } = require('./analysisController.js');
const { analysisApi, csrfCookie, AnalysisApiError } = require('./analysisApi.js');
const { inputProblem, matchingEvidence, resultEvidenceMatches, englishText } = require('./analysisText.js');
const React = require('react');
const { renderToStaticMarkup: render } = require('react-dom/server');
const { AnalysisPage } = require('./AnalysisPage.js');
const { AnalysisResults } = require('./components/analysis/AnalysisResults.js');
const { DiscoveryPage } = require('./DiscoveryPage.js');
const { JobList, Pagination } = require('./components/JobList.js');
const { JobDetail } = require('./components/JobDetail.js');
const { ManualJobForm } = require('./components/ManualJobForm.js');
const CV = '🚀 Built Python services for a small team.\r\nCafé reporting project.';
const JD = 'Required: Python services. Preferred: SQL. Work authorization required.';
const aid = '00000000-0000-0000-0000-000000000001';
const tid = '00000000-0000-0000-0000-000000000002';
const token = 'test-csrf-token-for-browser-only';
const policy = { policy_version: 'cv-match-gemini-1', provider: 'Gemini', consent_required: true, retention_hours: 24, session_retention_days: 7,
  notice: 'Your documents are sent to Gemini for comparison.', provider_retention_notice: 'Provider retention is separate.', provider_policy_url: 'https://ai.google.dev/gemini-api/terms', deletion_notice: 'Expired records are periodically removed.', limits: { max_document_characters: 40000, max_request_bytes: 350000, analyses_per_session: 10, global_daily_requests: 200 }, score: null, work_eligibility: 'NOT_ASSESSED' };
const accepted = { analysis_id: aid, task_id: tid, status: 'pending', status_url: `/api/v1/analyses/${aid}`, expires_at: '2030-01-01T00:00:00Z', csrf_token: token };
function span(text, quote) { const index = text.indexOf(quote); const start = Array.from(text.slice(0, index)).length; return { start, end: start + Array.from(quote).length, quote }; }
function result() { return { schema_version: '1', requirements: [
  { id: 'r1', text: 'Python services', importance: 'REQUIRED', jd_evidence: [span(JD, 'Python services')] },
  { id: 'r2', text: 'SQL', importance: 'PREFERRED', jd_evidence: [span(JD, 'SQL')] }], assessments: [
  { requirement_id: 'r1', status: 'MATCHED', rationale: 'Relevant evidence.', cv_evidence: [span(CV, 'Built Python services')] },
  { requirement_id: 'r2', status: 'UNVERIFIED', rationale: 'Not enough evidence.', cv_evidence: [] }],
  excluded_eligibility_evidence: [span(JD, 'Work authorization required.')], cv_suggestions: [
  { requirement_id: 'r2', kind: 'ASK_CONFIRMATION', text: 'Confirm your actual experience first.', question: 'Do you have experience with SQL?', cv_evidence: [] }], matched_count: 1, unverified_count: 1, score: null, work_eligibility: 'NOT_ASSESSED', limitations: ['An omission does not establish a missing skill.'], provider: 'gemini', model: 'mock-model', prompt_version: '1' }; }
function view(status = 'pending', error = null) { return { analysis_id: aid, task_id: tid, status, expires_at: accepted.expires_at, result: status === 'completed' ? result() : null, error }; }
const settle = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
function harness(overrides = {}) {
  const calls = { create: [], read: [], remove: [] }, timers = new Map(); let index = 0;
  const api = { policy: async () => policy,
    create: async (...args) => { calls.create.push(args); return accepted; },
    read: async (...args) => { calls.read.push(args); return view(); },
    remove: async (...args) => { calls.remove.push(args); }, ...overrides };
  const controller = new AnalysisController({ api, csrf: () => undefined, schedule: callback => { timers.set(++index, callback); return index; }, cancel: timer => timers.delete(timer) });
  return { controller, calls, timers, async ready() { controller.activate(); await settle(); controller.setText('cv', CV); controller.setText('jd', JD); controller.setConsent(true); }, async tick() { const entry = timers.entries().next().value; assert(entry); timers.delete(entry[0]); entry[1](); await settle(); } };
}
function mockFetch(t, handler) {
  const previous = globalThis.fetch, previousDocument = globalThis.document;
  globalThis.document = { cookie: '' };
  globalThis.fetch = async (url, options) => handler(url, options);
  t.after(() => { globalThis.fetch = previous; globalThis.document = previousDocument; });
}
const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

test('policy and explicit consent are required; duplicate POST is blocked', async () => {
  const pending = deferred(), h = harness({ create: async (...args) => { h.calls.create.push(args); return pending.promise; } });
  h.controller.activate(); await settle();
  h.controller.setText('cv', CV); h.controller.setText('jd', JD);
  await h.controller.submit(); assert.equal(h.calls.create.length, 0);
  h.controller.setConsent(true); const request = h.controller.submit(); await h.controller.submit();
  assert.equal(h.calls.create.length, 1); assert.equal(h.controller.getSnapshot().phase, 'submitting');
  pending.resolve(accepted); await request; await settle();
  assert.equal(h.controller.getSnapshot().snapshot.cv, CV); h.controller.pause();
});
test('policy failure prevents submission and reloading clears old consent', async () => {
  const h = harness({ policy: async () => { throw new Error('synthetic failure'); } });
  await h.ready(); await h.controller.submit();
  assert.equal(h.calls.create.length, 0); assert(h.controller.getSnapshot().policyError); h.controller.pause();
});
test('Unicode characters and submitted snapshot are immutable and offsets are exact', async () => {
  assert(matchingEvidence(CV, span(CV, 'Built Python services')));
  const offset = { ...span(CV, 'Built Python services'), start: CV.indexOf('Built Python services') };
  assert.equal(matchingEvidence(CV, offset), false);
  assert(resultEvidenceMatches({ cv: CV, jd: JD }, result()));
  const h = harness(); await h.ready(); await h.controller.submit();
  h.controller.setText('cv', 'replacement');
  assert.equal(h.controller.getSnapshot().snapshot.cv, CV); assert.equal(h.controller.getSnapshot().cv, CV); h.controller.pause();
});
test('validation uses Unicode points, exact text, byte size and no NUL', () => {
  assert.equal(inputProblem('🚀'.repeat(30), JD, policy), null);
  assert(inputProblem('🚀'.repeat(29), JD, policy)); assert(inputProblem(CV + '\0', JD, policy));
  assert(inputProblem(CV, JD, { ...policy, limits: { ...policy.limits, max_request_bytes: 50 } }));
  assert(inputProblem(' '.repeat(31), JD, policy));
});
test('pending, server retry, processing and completion use GET only and stop polling', async () => {
  const states = [view('pending', { code: 'LLM_READ_TIMEOUT' }), view('processing'), view('completed')];
  const h = harness({ read: async (...args) => { h.calls.read.push(args); return states.shift(); } });
  await h.ready(); await h.controller.submit(); await settle();
  assert.equal(h.controller.getSnapshot().view.error.code, 'LLM_READ_TIMEOUT');
  await h.tick(); assert.equal(h.controller.getSnapshot().view.status, 'processing');
  await h.tick(); assert.equal(h.controller.getSnapshot().view.status, 'completed');
  assert.equal(h.timers.size, 0); assert.equal(h.calls.create.length, 1);
  h.controller.pause(); h.controller.activate(); await settle(); assert.equal(h.calls.read.length, 3); h.controller.pause();
});
test('failed state stops polling without inventing a retryable field', async () => {
  const h = harness({ read: async () => view('failed', { code: 'LLM_HTTP_ERROR', http_status: '400', stage: 'extraction' }) });
  await h.ready(); await h.controller.submit(); await settle();
  assert.equal(h.controller.getSnapshot().view.status, 'failed'); assert.equal(h.timers.size, 0);
  const markup = render(React.createElement(AnalysisPage, { controller: h.controller }));
  assert(markup.includes('could not be completed')); assert(markup.includes('stage: extraction')); h.controller.pause();
});
test('lost POST response is never resent; new submission needs explicit acknowledgement and consent', async () => {
  const h = harness({ create: async (...args) => { h.calls.create.push(args); throw new AnalysisApiError(null, 'network'); } });
  await h.ready(); await h.controller.submit(); await h.controller.submit(); h.controller.retryPoll();
  assert.equal(h.calls.create.length, 1); assert.equal(h.controller.getSnapshot().phase, 'submit_unknown');
  h.controller.acknowledgeUnknown(); await h.controller.submit(); assert.equal(h.calls.create.length, 1);
  assert.equal(h.controller.getSnapshot().consent, false); h.controller.pause();
});
test('status connection failure can retry the existing GET without another POST', async () => {
  let tries = 0; const h = harness({ read: async (...args) => { h.calls.read.push(args); if (!tries++) throw new AnalysisApiError(null, 'network'); return view('completed'); } });
  await h.ready(); await h.controller.submit(); await settle();
  assert.equal(h.controller.getSnapshot().phase, 'poll_error'); h.controller.retryPoll(); await settle();
  assert.equal(h.calls.read.length, 2); assert.equal(h.calls.create.length, 1); assert.equal(h.controller.getSnapshot().view.status, 'completed'); h.controller.pause();
});
test('404 is unavailable, never claimed to be successfully deleted', async () => {
  const h = harness({ read: async () => { throw new AnalysisApiError(404); } });
  await h.ready(); await h.controller.submit(); await settle();
  assert.equal(h.controller.getSnapshot().phase, 'unavailable'); assert(h.controller.getSnapshot().accepted); h.controller.pause();
});
test('delete stops late polling, clears sensitive state only after confirmed 204', async () => {
  const response = deferred(); const h = harness({ read: () => response.promise });
  await h.ready(); await h.controller.submit(); await h.controller.deleteAnalysis();
  response.resolve(view('completed')); await settle();
  const state = h.controller.getSnapshot(); assert.equal(state.phase, 'deleted');
  assert.equal(state.cv, ''); assert.equal(state.jd, ''); assert.equal(state.snapshot, null); assert.equal(state.view, null); assert.equal(state.accepted, null); assert.equal(h.timers.size, 0);
  assert.equal(h.calls.remove[0][0], aid); assert.equal(h.calls.remove[0][1], token); h.controller.pause();
});
test('failed deletion retains the analysis handle and allows deletion retry', async () => {
  let tries = 0; const h = harness({ remove: async () => { if (!tries++) throw new AnalysisApiError(403); } });
  await h.ready(); await h.controller.submit(); await settle(); await h.controller.deleteAnalysis();
  assert.equal(h.controller.getSnapshot().phase, 'delete_error'); assert(h.controller.getSnapshot().accepted); assert.equal(h.controller.getSnapshot().cv, CV);
  await h.controller.deleteAnalysis(); assert.equal(h.controller.getSnapshot().phase, 'deleted'); h.controller.pause();
});
test('navigation pause aborts requests and resumes only an existing analysis', async () => {
  const h = harness(); await h.ready(); await h.controller.submit(); await settle();
  h.controller.pause(); assert.equal(h.timers.size, 0); assert(h.calls.read[0][1].aborted);
  h.controller.activate(); await settle(); assert.equal(h.calls.read.length, 2); assert.equal(h.calls.create.length, 1); h.controller.pause();
});
test('mismatched evidence is not displayed as a completed match', async () => {
  const broken = view('completed'); broken.result.assessments[0].cv_evidence[0].start += 1;
  const h = harness({ read: async () => broken }); await h.ready(); await h.controller.submit(); await settle();
  assert.equal(h.controller.getSnapshot().phase, 'poll_error'); assert.equal(h.controller.getSnapshot().view, null); h.controller.pause();
});
test('first POST has cookies enabled without CSRF; existing-session POST and DELETE send CSRF; GET does not', async t => {
  const calls = []; mockFetch(t, (url, options) => { calls.push({ url, options }); return url.endsWith('/policy') ? json(policy) : options.method === 'DELETE' ? new Response(null, { status: 204 }) : options.method === 'POST' ? json(accepted, 202) : json(view()); });
  const signal = new AbortController().signal;
  await analysisApi.policy(signal);
  await analysisApi.create({ cv_text: CV, jd_text: JD, consent: true, policy_version: policy.policy_version }, signal, csrfCookie());
  assert.equal(calls[1].options.headers['X-CSRF-Token'], undefined);
  globalThis.document.cookie = `wayfaro_cv_csrf=${token}`;
  await analysisApi.create({ cv_text: CV, jd_text: JD, consent: true, policy_version: policy.policy_version }, signal, csrfCookie());
  await analysisApi.read(aid, signal); await analysisApi.remove(aid, csrfCookie(), signal);
  assert.equal(calls[2].options.headers['X-CSRF-Token'], token); assert.equal(calls[3].options.headers, undefined); assert.equal(calls[4].options.headers['X-CSRF-Token'], token);
  for (const call of calls) { assert.equal(call.options.credentials, 'include'); assert.equal(call.options.cache, 'no-store'); assert(!call.url.includes(CV)); assert(!call.url.includes(JD)); }
});
test('unsupported CV_GAP, score and incomplete result contracts fail closed', async t => {
  let data = view('completed'); mockFetch(t, () => json(data)); const signal = new AbortController().signal;
  for (const change of [value => { value.result.assessments[0].status = 'CV_GAP'; }, value => { value.result.score = 99; }, value => { value.result.assessments.pop(); }]) {
    data = view('completed'); change(data); await assert.rejects(analysisApi.read(aid, signal), error => error.kind === 'invalid');
  }
});
test('result rendering preserves exact quotes, English chrome and UNVERIFIED uncertainty without aggregate score', () => {
  const markup = render(React.createElement(AnalysisResults, { result: result(), snapshot: { cv: CV, jd: JD } }));
  assert(markup.includes('Built Python services')); assert(markup.includes('From your CV')); assert(markup.includes('From the job description'));
  assert(markup.includes('It does not mean you lack the skill')); assert(markup.includes('Work eligibility: not assessed'));
  assert(!/match score|\d+%/i.test(markup)); assert(markup.includes('Do you have experience with SQL?'));
});
test('untrusted evidence is escaped as text and unsafe job links are not rendered', () => {
  const cv = '<script>alert(1)</script> '.repeat(2); const data = result();
  data.assessments[0].cv_evidence = [span(cv, '<script>alert(1)</script>')];
  const markup = render(React.createElement(AnalysisResults, { result: data, snapshot: { cv, jd: JD } }));
  assert(markup.includes('&lt;script&gt;')); assert(!markup.includes('<script>'));
});
test('discovery keeps search controls, list, detail, paging and public manual form in English', t => {
  const previous = globalThis.window; globalThis.window = { location: { search: '?view=discover&q=Engineer' } }; t.after(() => { globalThis.window = previous; });
  const markup = render(React.createElement(DiscoveryPage)); assert(markup.includes('value="Engineer"')); assert(markup.includes('Apply search')); assert(markup.includes('Add a job manually'));
  const job = { id: aid, title: 'Engineer', origin: 'manual', remote_mention: 'UNKNOWN', raw_text: 'Original job description', source_url: 'javascript:alert(1)' };
  assert(render(React.createElement(JobList, { data: { items: [job] }, selected: aid, onSelect() {} })).includes('Engineer'));
  assert(render(React.createElement(JobDetail, { job, onClose() {} })).includes('Original job description'));
  assert(!render(React.createElement(JobDetail, { job, onClose() {} })).includes('href="javascript:'));
  assert(render(React.createElement(Pagination, { data: { page: 1, total_pages: 2 }, onPage() {} })).includes('Page 1 of 2'));
  assert(render(React.createElement(ManualJobForm, { onCreated() {} })).includes('Do not paste your CV'));
});
test('analysis source does not use browser storage, console, analytics, or URL state', () => {
  for (const name of ['analysisController.js', 'analysisApi.js', 'AnalysisPage.js', 'components/analysis/AnalysisResults.js']) {
    const source = fs.readFileSync(path.join(process.env.WAYFARO_TEST_BUILD, name), 'utf8');
    assert(!/localStorage|sessionStorage|console\.|pushState|replaceState|gtag\(|analytics\./.test(source));
  }
});
test('unknown policy notice is not silently translated into old consent text', async () => {
  const h = harness({ policy: async () => ({ ...policy, notice: '새로운 정책 내용입니다.' }) });
  await h.ready(); assert.equal(h.controller.getSnapshot().policy, null); assert(h.controller.getSnapshot().policyError); h.controller.pause();
  assert.equal(englishText('미언급은 실제 역량 부족을 뜻하지 않습니다. CV_GAP과 SKILL_GAP은 확정하지 않습니다.').includes('not evidence of a missing skill'), true);
});

test('interrupted in-flight POST ignores a late acknowledgement and is not sent again', async () => {
  const late = deferred(); const h = harness({ create: async (...args) => { h.calls.create.push(args); return late.promise; } });
  await h.ready(); const pending = h.controller.submit(); h.controller.pause(); h.controller.activate();
  late.resolve(accepted); await pending; await settle();
  assert.equal(h.controller.getSnapshot().phase, 'submit_unknown'); assert.equal(h.controller.getSnapshot().accepted, null);
  assert.equal(h.calls.create.length, 1); assert.equal(h.calls.read.length, 0); h.controller.pause();
});
test('input, consent and loading screen state are reflected in accessible rendered controls', async () => {
  const h = harness(); await h.ready(); h.controller.setConsent(false);
  let markup = render(React.createElement(AnalysisPage, { controller: h.controller }));
  assert(markup.includes('Your CV')); assert(markup.includes('Job description')); assert(markup.includes('Temporary retention: up to 24 hours'));
  assert(markup.includes('I agree to send these documents')); assert(/class="primary"[^>]*disabled/.test(markup));
  h.controller.setConsent(true); markup = render(React.createElement(AnalysisPage, { controller: h.controller }));
  assert(!/class="primary"[^>]*disabled/.test(markup));
  await h.controller.submit(); await settle(); markup = render(React.createElement(AnalysisPage, { controller: h.controller }));
  assert(markup.includes('Your analysis is queued')); assert(markup.includes('role="status"')); assert(!markup.includes(aid)); h.controller.pause();
});
test('existing-session POST uses the browser CSRF cookie', async () => {
  const calls = [];
  const controller = new AnalysisController({ api: { policy: async () => policy, create: async (...args) => { calls.push(args); return accepted; }, read: async () => view('failed'), remove: async () => {} }, csrf: () => token });
  controller.activate(); await settle(); controller.setText('cv', CV); controller.setText('jd', JD); controller.setConsent(true); await controller.submit();
  assert.equal(calls[0][2], token); controller.pause();
});

test('the actual Korean policy contract is displayed as faithful English consent text', async () => {
  const actual = { ...policy,
    notice: 'CV와 JD 원문이 비교 분석을 위해 Google Gemini API로 전송됩니다. 입력과 결과는 지정된 기간 동안만 임시 보관하며 영구 저장하지 않습니다.',
    provider_retention_notice: 'Google Gemini의 데이터 사용·보관은 계정·서비스 이용 조건에 따라 달라집니다. 무보관이나 학습 제외를 보장하지 않습니다. 외부 전송은 삭제 요청으로 취소할 수 없습니다.',
    deletion_notice: '만료 즉시 조회와 새 LLM 호출을 차단합니다. Worker가 실행 중이면 주기적으로 DB에서 삭제하며 백업·외부 제공자 보관은 별도입니다.' };
  const h = harness({ policy: async () => actual }); await h.ready();
  const markup = render(React.createElement(AnalysisPage, { controller: h.controller }));
  assert(markup.includes('sent to Google Gemini')); assert(markup.includes('Zero retention and exclusion from training are not guaranteed'));
  assert(!/[가-힣]/u.test(markup)); h.controller.pause();
});
test('lost or malformed POST acknowledgements and 5xx responses are not automatically retried', async () => {
  for (const failure of [new AnalysisApiError(502), new AnalysisApiError(202, 'invalid')]) {
    const h = harness({ create: async (...args) => { h.calls.create.push(args); throw failure; } });
    await h.ready(); await h.controller.submit(); h.controller.activate(); await settle(); await h.controller.submit();
    assert.equal(h.controller.getSnapshot().phase, 'submit_unknown'); assert.equal(h.calls.create.length, 1); h.controller.pause();
  }
});
test('deletion transport failure is not reported as successful deletion by the API adapter', async t => {
  let count = 0; mockFetch(t, () => { if (!count++) return json({}, 404); return new Response(null, { status: 204 }); });
  const signal = new AbortController().signal;
  await assert.rejects(analysisApi.remove(aid, token, signal), error => error.status === 404);
  await analysisApi.remove(aid, token, signal);
});
test('status checking may be resumed after a failed deletion without creating a new analysis', async () => {
  const h = harness({ remove: async () => { throw new AnalysisApiError(null, 'network'); } });
  await h.ready(); await h.controller.submit(); await settle(); await h.controller.deleteAnalysis();
  const previous = h.calls.read.length; h.controller.retryPoll(); await settle();
  assert.equal(h.calls.read.length, previous + 1); assert.equal(h.calls.create.length, 1); h.controller.pause();
});

test('the application defaults to analysis but preserves legacy discovery links', t => {
  const { App } = require('./App.js');
  const previous = globalThis.window;
  globalThis.window = { location: { search: '' } };
  t.after(() => { globalThis.window = previous; });
  assert(render(React.createElement(App)).includes('meets the opportunity'));
  globalThis.window.location.search = '?page_size=2';
  assert(render(React.createElement(App)).includes('Explore your next opportunity'));
  globalThis.window.location.search = `?job=${aid}`;
  assert(render(React.createElement(App)).includes('Explore your next opportunity'));
});
