from geo_optimizer.core.collection.normalize import batch_from_dict, batch_to_benchmark_answers


def test_manual_answer_retains_supplied_citation_urls():
    payload = {'answers': [{'prompt': 'Find a provider', 'answer_text': 'An answer', 'provider': 'chatgpt', 'citation_urls': ['https://example.com/source']}]}
    rows = batch_to_benchmark_answers(batch_from_dict(payload))
    assert rows[0]['citation_urls'] == ['https://example.com/source']
