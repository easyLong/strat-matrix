"""Export pagination and CSV safety preserve the result-query contract."""
from contextlib import contextmanager
import csv
from datetime import date,datetime
import io
import unittest
from unittest.mock import MagicMock,patch
from app.content_planning.services import result_export as exports
from app.content_planning.services.result_scope import ResultQuery,compile_scope

def item(identity):
    return dict(id=identity,account_id='A',account_name='Account A',publish_date=date(2026,11,4),
        batch_code='B',plan_type='manual',topic_id='T',topic_title='Title',outline='Line one\nLine two',
        content_type='金融科普',production_status='planned',batch_created_at=datetime(2026,11,3))

class ExportTests(unittest.TestCase):
    def test_export_pages_by_records_and_preserves_filters(self):
        query=ResultQuery(mode='all',page_size=2,unit='records',filters={'planType':'manual'})
        first=dict(items=[item(1),item(2)],total=3,latest_operations={})
        with patch.object(exports,'export_page',return_value=dict(items=[item(3)],total=3,latest_operations={})) as fetch:
            text=''.join(exports.export_csv(query,first))
        rows=list(csv.DictReader(io.StringIO(text.lstrip('\ufeff'))))
        self.assertEqual(len(rows),3);fetch.assert_called_once()
        self.assertEqual(fetch.call_args.args[0].page,2)
        self.assertEqual(fetch.call_args.args[0].filters,query.filters)
        self.assertEqual(rows[0]['选题大纲'],'Line one\nLine two')

    def test_latest_operation_is_preserved_even_with_legacy_clock_skew(self):
        row=item(1)
        operation=dict(created_at=datetime(2026,11,2),adjustment_source='人工替换',created_by='User',
                       old_topic_title='Old',new_topic_title='New',reason='Reason')
        text=''.join(exports.export_csv(ResultQuery(mode='all'),dict(items=[row],total=1,latest_operations={1:operation})))
        result=next(csv.DictReader(io.StringIO(text.lstrip('\ufeff'))))
        self.assertEqual(result['最新操作'],'人工替换');self.assertEqual(result['操作人'],'User')

    def test_csv_cells_do_not_execute_spreadsheet_formulas(self):
        values=['=1+1','+1','@formula','-2','plain','commas,and "quotes"']
        row=next(csv.reader(io.StringIO(exports.csv_line(values))))
        self.assertEqual(row[:4],["'"+v for v in values[:4]])
        self.assertEqual(row[4:],values[4:])

    def test_prepare_export_freezes_upper_id_and_clears_current_page(self):
        cursor=MagicMock();cursor.fetchone.return_value={'upper_id':99}
        @contextmanager
        def connection():
            db=MagicMock();db.cursor.return_value.__enter__.return_value=cursor;yield db
        with patch.object(exports,'connection',connection):
            query=exports.prepare_export(ResultQuery(mode='batch',batch_id=3,page=8))
        self.assertEqual(query.page,1);self.assertEqual(query.unit,'records')
        where,params,_,_=compile_scope(query)
        self.assertIn('i.id<=%s',where);self.assertEqual(params[-1],99)

if __name__=='__main__':unittest.main()
