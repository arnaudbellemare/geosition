const test = require('node:test');
const assert = require('node:assert/strict');
const action = require('../src/geo_optimizer/mcp/auth0-post-login.cjs');
const resource = 'https://www.geositionai.com/mcp';
const event = () => ({resource_server:{identifier:resource}, client:{client_id:'chatgpt'},
  user:{user_id:'auth0|mom'}, secrets:{GEOSITION_REDIRECT_SECRET:'test-secret'}});
test('redirects only the GEOSITION resource using a signed context', async () => {
  let encoded, target;
  const api = {access:{deny:() => { throw new Error('unexpected denial'); }}, redirect:{
    encodeToken: (v) => {encoded=v; return 'signed-context';},
    sendUserTo: (url, options) => {target={url, options};}}};
  await action.onExecutePostLogin(event(), api);
  assert.equal(encoded.payload.client_id, 'chatgpt');
  assert.equal(encoded.payload.resource, resource);
  assert.equal(target.options.query.session_token, 'signed-context');
  assert.equal(target.url, 'https://www.geositionai.com/oauth/auth0/start');
});
test('rejects denial and changed identities before continuing', async () => {
  let denied = 0;
  let result = {decision:'approve', sub:'auth0|mom', client_id:'chatgpt', resource, iss:resource};
  const api = {access:{deny:() => {denied++;}}, redirect:{validateToken:() => result}};
  await action.onContinuePostLogin(event(), api);
  assert.equal(denied, 0);
  result = {...result, client_id:'other'};
  await action.onContinuePostLogin(event(), api);
  assert.equal(denied, 1);
  result = {...result, client_id:'chatgpt', decision:'deny'};
  await action.onContinuePostLogin(event(), api);
  assert.equal(denied, 2);
});
