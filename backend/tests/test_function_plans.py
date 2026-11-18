import copy
import pytest
from pydantic import ValidationError
from conftest import auth
from nexus.interfaces import Blueprint,catalog
from test_interfaces import payload

def plan(feature):
    return {'feature_id':feature['id'],'owner':'Platform design owner','phase':'planned','values':{f['id']:f['default'] for f in feature['fields']},'checks':{k:False for k in ['scope','access','feedback','handoff']},'notes':'Long-term UI specification; runtime implementation pending.'}

@pytest.mark.parametrize('spec',catalog()['modules'],ids=lambda s:s['id'])
def test_all_module_function_plans_save_with_real_revisions(ctx,spec):
    headers,_=auth(ctx);body=payload(spec);body['config']['function_plans']=[plan(f) for f in spec['features']]
    response=ctx['client'].post('/v1/workbench',headers=headers,json=body)
    assert response.status_code==201,response.text
    row=response.json();assert len(row['config']['function_plans'])==12
    fp=body['config']['function_plans'][0];fp['checks']={k:True for k in fp['checks']};fp['phase']='ui_reviewed'
    updated=ctx['client'].put('/v1/workbench/'+row['id'],headers=headers,json={**body,'expected_version':row['version']})
    assert updated.status_code==200,updated.text
    assert updated.json()['version']==2
    assert updated.json()['config']['function_plans'][0]['phase']=='ui_reviewed'

def test_catalog_has_216_unique_function_screens():
    features=[f for m in catalog()['modules'] for f in m['features']]
    assert len(features)==216 and len({f['id'] for f in features})==216
    assert sum(len(f['fields']) for f in features)==648
    for f in features:
        assert len(f['roles'])>=3 and len(f['states'])==8 and len(f['steps'])==6
        assert f['planned_path'].startswith('/v1/planned/') and f['runtime_activated'] is False

def test_function_planning_cannot_bypass_review_or_cross_module_scope():
    specs=catalog()['modules'];config=payload(specs[0])['config'];p=plan(specs[0]['features'][0]);config['function_plans']=[p];p['phase']='ui_reviewed'
    with pytest.raises(ValidationError):Blueprint.model_validate(config)
    config['function_plans']=[plan(specs[1]['features'][0])]
    with pytest.raises(ValidationError):Blueprint.model_validate(config)
    config['function_plans']=[plan(specs[0]['features'][0])]*2
    with pytest.raises(ValidationError):Blueprint.model_validate(config)

def test_function_plans_reject_raw_secrets_unknown_fields_and_nonfinite_numbers():
    for spec in catalog()['modules']:
        for feature in spec['features']:
            config=payload(spec)['config'];p=plan(feature);config['function_plans']=[p]
            for field in feature['fields']:
                if field['type'] not in ['reference','number']:continue
                bad=copy.deepcopy(config);bad['function_plans'][0]['values'][field['id']]='raw-secret' if field['type']=='reference' else 'NaN'
                with pytest.raises(ValidationError):Blueprint.model_validate(bad)
    config=payload(catalog()['modules'][0])['config'];p=plan(catalog()['modules'][0]['features'][0]);config['function_plans']=[p];p['values']['unexpected']='x'
    with pytest.raises(ValidationError):Blueprint.model_validate(config)
