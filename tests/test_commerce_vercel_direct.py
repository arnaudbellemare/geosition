import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from geo_optimizer.cli.main import cli
from geo_optimizer.core.commerce_vercel_direct import fetch_vercel_correlation
from geo_optimizer.models.results.commerce_site import CommerceSiteReport

START='2026-11-14T00:47:00Z'
END='2026-11-14T00:49:00Z'


def provider_outputs(*, host='www.robel-art.com', verified=1, more=False):
    req={'requestId':'req-1','requestHostname':host,'requestPath':'/shop.html','requestMethod':'GET',
         'timestamp':'2026-11-14T00:47:43.722Z','wafAction':'allow','httpStatus':304}
    log='\n'.join(json.dumps(x) for x in [{'type':'request','data':req},{'type':'summary','recordsReturned':1,
        'pagination':{'hasMore':more},'excludedIntervals':[],'timeRange':{'start':START,'end':END}}])
    metrics=json.dumps({'query':{'metric':'vercel.ai_traffic.count','aggregation':'count','groupBy':['botName']},'summary':[{'botName':'chatgpt-operator','vercel_ai_traffic_count_count':verified}],
        'meta':{'effectiveTimeRange':{'start':START,'end':END}},'queryId':'test-query'})
    return log,metrics


def call(outputs):
    def runner(executable,args): return outputs[0] if args[0]=='logs' else outputs[1]
    return fetch_vercel_correlation('https://www.robel-art.com/shop.html',executable='vercel',scope='team',
        project='shop',request_id='req-1',since=START,until=END,runner=runner)


def test_authenticated_provider_correlation_keeps_signature_scope_explicit():
    evidence=call(provider_outputs())
    assert evidence['classification']=='provider_verified_correlated'
    assert evidence['http_status']==304 and evidence['firewall_action']=='allow'
    assert 'Individual signature' in evidence['limit']


def test_incomplete_mismatched_or_unverified_provider_data_is_rejected():
    for outputs in (provider_outputs(host='other.example'),provider_outputs(verified=0),provider_outputs(more=True)):
        with pytest.raises(ValueError): call(outputs)


def test_audit_direct_evidence_is_presented_without_current_access_claim():
    report=CommerceSiteReport(url='https://www.robel-art.com/shop.html', pages=[{'url':'https://www.robel-art.com/shop.html'}],
        coverage={'pages_audited':1,'pending':0},browser_access={'verified_access':'unknown'},recommendations=[])
    record=call(provider_outputs())
    with patch('geo_optimizer.core.commerce_site.run_site_audit',return_value=report), patch('geo_optimizer.core.commerce_vercel_direct.fetch_vercel_correlation',return_value=record):
        result=CliRunner().invoke(cli,['commerce-audit','--site','--url',report.url,'--format','json','--vercel-project','shop','--vercel-scope','team','--vercel-request-id','req-1','--vercel-since',START,'--vercel-until',END])
    assert result.exit_code==0, result.output
    access=json.loads(result.output)['browser_access']
    assert access['verified_access']=='unknown'
    assert access['provider_evidence']['classification']=='provider_verified_correlated'
