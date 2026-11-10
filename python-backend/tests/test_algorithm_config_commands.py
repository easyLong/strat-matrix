import json
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
import pytest
from app.content_planning import algorithm_config_commands as service
from app.content_planning.models import StrategyConfig

def test_algorithm_command_reuses_receipt_and_preserves_business_fields():
    db,cursor=MagicMock(),MagicMock();db.__enter__.return_value=db;db.cursor.return_value=cursor;cursor.__enter__.return_value=cursor
    base=StrategyConfig(marketing_max=3,hotspot_ratio=20).model_dump(mode='json')
    algorithm={k:v for k,v in base.items() if k not in service.BUSINESS_FIELDS}
    algorithm['rolling_window_posts']=15
    # Keep the current schema's algorithm fields; unknown fields are intentionally rejected.
    algorithm={k:v for k,v in algorithm.items() if k in StrategyConfig.model_fields}
    payload=service.ConfigCommand(command_id='C1',expected_version=4,algorithm_config=algorithm,actor='UM1')
    saved=[None];current={'config_json':json.dumps(base),'version':4};selected=[None]
    def execute(sql,params=()):
        if sql.startswith('SELECT config_json'): selected[0]=current
        elif sql.startswith('SELECT * FROM godp_algorithm_config_command'):selected[0]=saved[0]
        elif sql.startswith('INSERT INTO godp_algorithm_config_command'):saved[0]=dict(zip(('command_id','request_hash','result_json'),params))
    cursor.execute.side_effect=execute;cursor.fetchone.side_effect=lambda:selected[0]
    with patch.object(service,'connection',return_value=db):
        first=service.apply_config_command(payload);second=service.apply_config_command(payload)
        assert first==second and first['version']==5
        assert first['config']['marketing_max']==3
        assert first['config']['hotspot_ratio']==20
        db.commit.assert_called_once()
        with pytest.raises(HTTPException):
            service.apply_config_command(payload.model_copy(update={'actor':'OTHER'}))
