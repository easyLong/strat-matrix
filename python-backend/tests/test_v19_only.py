"""Only V19 may execute; historical policy fingerprints and reads stay intact."""
from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app import matching_executor_worker as worker, matching_policy as policies
from app.account_profile import canonical_json
from app.consolidate_v19 import production_document
from app.matching_contracts import MatchingPolicyDocument, MatchingQualityOptions, PolicyCreate
from app.matching_quality import IMPLEMENTATION_KEY
from app.system_config import override_config
import test_matching_quality as quality_fixtures


def test_worker_registers_only_v19_and_saves_result():
    job = {'task_id': 1}
    execute = MagicMock(return_value=object())
    with override_config({}), patch.object(worker, 'EXECUTORS', {IMPLEMENTATION_KEY: execute}), \
         patch.object(worker, 'claim_task', side_effect=[{'job': job, 'next_after_id': 1}, {'job': None}]) as claim, \
         patch.object(worker, 'save_evaluation', return_value={'status': 'evaluated', 'version': 3}) as save:
        assert worker.run_once() == 0
    assert all(call.kwargs['implementation_key'] == IMPLEMENTATION_KEY for call in claim.call_args_list)
    execute.assert_called_once_with(job)
    save.assert_called_once()
    assert set(worker.EXECUTORS) == {IMPLEMENTATION_KEY}


@pytest.mark.parametrize('key', ['builtin-cosine-balanced-v1', 'builtin-cosine-portfolio-v2', 'unknown'])
def test_legacy_policy_is_readable_but_cannot_create_approve_or_execute(key):
    raw = quality_fixtures.QualityPolicyAndAllocationTests().policy().model_dump(mode='json')
    raw.update(implementation_key=key, quality=None)
    encoded = canonical_json(raw)
    row = dict(document_json=encoded, document_hash=policies.digest(encoded))
    document = policies.intact_document(row)
    assert document.implementation_key == key
    assert policies.implementation_approval_errors(document)
    with pytest.raises(HTTPException):
        policies.require_v19(document)
    with patch.object(policies, 'connection') as connection, pytest.raises(HTTPException):
        policies.create_policy(PolicyCreate(policy_key='legacy', expected_latest_version=0, document=document))
    connection.assert_not_called()


def test_preview_default_cannot_silently_become_production_and_draft_mapping_is_rejected():
    assert MatchingQualityOptions().evaluation_only is True
    with pytest.raises(ValidationError):
        MatchingQualityOptions(evaluation_only=False, mapping_mode='draft_preview')
    with pytest.raises(ValidationError):
        MatchingQualityOptions(evaluation_only='false')


def test_production_conversion_preserves_reviewed_rules_and_original_document():
    raw = quality_fixtures.QualityPolicyAndAllocationTests().policy().model_dump(mode='json')
    encoded = canonical_json(raw)
    row = dict(status='approved', document_json=encoded, document_hash=policies.digest(encoded))
    before = deepcopy(row)
    production = production_document(row)
    assert row == before
    assert production.quality.evaluation_only is False
    assert production.quality.model_copy(update={'evaluation_only': True}) == MatchingQualityOptions.model_validate(raw['quality'])
    assert policies.implementation_approval_errors(production) == []
    row['status'] = 'draft'
    with pytest.raises(ValueError):
        production_document(row)


def test_v19_capacity_contract_rejects_unexecuted_parameters():
    document = quality_fixtures.QualityPolicyAndAllocationTests().policy()
    document.decisions['ALG-05'].parameters['global_reuse_penalty'] = 1
    assert policies.implementation_approval_errors(document)


def test_production_v19_can_pass_formal_commit_boundary():
    fixture = quality_fixtures.commit_fixture.PlanningResultTransactionTests()
    fixture.setUp()
    try:
        document = quality_fixtures.QualityPolicyAndAllocationTests().policy()
        document.quality.evaluation_only = False
        with patch.object(quality_fixtures.commit_fixture.service, 'intact_document', return_value=document):
            result = quality_fixtures.commit_fixture.service.commit_pipeline_result(501, 7)
        assert result['batch_id'] == 9001
    finally:
        fixture.doCleanups()


def test_production_result_requires_production_evidence():
    fixture = quality_fixtures.QualityResultGuardTests()
    cursor, task, result, inputs, document, report = fixture.fixture()
    document.quality.evaluation_only = False
    with pytest.raises(HTTPException):
        quality_fixtures.validate_quality_evaluation(cursor, task, result, inputs, document)
    report['evaluation_only'] = False
    fixture.bind(cursor, report, result, task)
    quality_fixtures.validate_quality_evaluation(cursor, task, result, inputs, document)
