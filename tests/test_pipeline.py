"""Offline tests for intake, acquisition boundaries and calibration persistence."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import acquire
import audit_public
import build_places
import apply_review_results as calibration
import ingest


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.payload=json.loads((ROOT/'examples/intake.json').read_text())
    def tearDown(self): self.tmp.cleanup()
    def test_repeat_ingest_and_delivery_is_idempotent(self):
        first=ingest.process(self.payload,self.root,True,'2000-1-1')
        raw=self.root/first['delivered_file']; original=raw.read_bytes()
        second=ingest.process(self.payload,self.root,True,'2000-1-1')
        self.assertIsNone(second['delivered_file'])
        self.assertEqual(len(list((self.root/'raw').glob('*.md'))),1)
        self.assertEqual(len(ingest.read_rows(self.root/'data/acquisition/ingest-ledger.jsonl')),1)
        self.assertEqual(len(ingest.read_rows(self.root/'data/acquisition/retrieval-ledger.jsonl')),1)
        self.assertEqual(raw.read_bytes(),original)
    def test_new_capture_preserves_previous_version(self):
        ingest.process(self.payload,self.root)
        files=list((self.root/'data/acquisition/raw').rglob('1.json')); before=files[0].read_bytes()
        changed=copy.deepcopy(self.payload); changed['sources'][0]['text']+=' More context.'
        ingest.process(changed,self.root)
        self.assertEqual(files[0].read_bytes(),before)
        self.assertEqual(len(list((self.root/'data/acquisition/raw').rglob('*.json'))),2)
        self.assertEqual(len(ingest.read_rows(self.root/'data/acquisition/ingest-ledger.jsonl')),1)
    def test_missing_evidence_is_not_delivered(self):
        self.payload['places'][0]['evidence'][0]['quote']='not in the source'
        result=ingest.process(self.payload,self.root,True)
        self.assertEqual(result['staged_places'],0)
        self.assertEqual(result['needs_review'],2)
        self.assertFalse((self.root/'raw').exists())
    def test_unknown_city_is_not_guessed(self):
        self.payload['places'][0]['city']=''
        result=ingest.process(self.payload,self.root,True)
        settings=json.loads((self.root/'config/raw-update-metadata.local.json').read_text())
        self.assertEqual(next(iter(settings.values()))['示例纸页咖啡']['city'],'')
        self.assertEqual(result['staged_places'],1)
    def test_duplicate_place_names_merge_sources_and_food(self):
        extra=copy.deepcopy(self.payload['places'][0]); extra['recommendedFood']=['示例茶']
        self.payload['places'].append(extra)
        result=ingest.process(self.payload,self.root,True)
        text=(self.root/result['delivered_file']).read_text()
        self.assertEqual(result['staged_places'],1)
        self.assertIn('示例拿铁',text); self.assertIn('示例茶',text)
    def test_existing_filename_is_never_overwritten(self):
        (self.root/'raw').mkdir(); old=self.root/'raw/2000-1-1_update.md'; old.write_text('kept')
        result=ingest.process(self.payload,self.root,True,'2000-1-1')
        self.assertTrue(result['delivered_file'].endswith('_update-2.md'))
        self.assertEqual(old.read_text(),'kept')
    def test_credentialed_source_url_rejected_before_writes(self):
        self.payload['sources'][0]['canonical_url']='https://user:pass@example.org/note'
        with self.assertRaises(ValueError): ingest.process(self.payload,self.root)
        self.assertEqual(list(self.root.iterdir()),[])


class AcquisitionTests(unittest.TestCase):
    def test_metadata_is_the_default_and_download_explicit(self):
        url='https://www.douyin.com/video/0000000000000000000'
        self.assertIn('--metadata-only',acquire.invocation(Path('skill'),url,Path('run'))[2])
        self.assertNotIn('--metadata-only',acquire.invocation(Path('skill'),url,Path('run'),True)[2])
        xhs='https://www.xiaohongshu.com/explore/example'
        self.assertIn('--skip-media',acquire.invocation(Path('skill'),xhs,Path('run'))[2])
    def test_search_and_account_pages_are_not_supported(self):
        for url in ('https://www.douyin.com/user/example','https://www.xiaohongshu.com/search_result','http://example.org/note'):
            with self.assertRaises(ValueError): acquire.route(url)
    def test_fake_executor_records_transport_not_text_completeness(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); skill=root/'skill'; (skill/'scripts').mkdir(parents=True)
            (skill/'SKILL.md').write_text('test fixture')
            (skill/'scripts/douyin_download.py').write_text('import pathlib,sys,json\np=pathlib.Path(sys.argv[2]+".metadata.json");p.write_text(json.dumps({"aweme_id":"fixture-video"}))\n')
            output,result=acquire.acquire(skill,'https://www.douyin.com/video/0000000000000000000',root)
            self.assertEqual(result['capture_status'],'success')
            self.assertEqual(result['content_state'],'metadata_only')
            self.assertEqual(result['source_id'],'douyin:fixture-video')
            self.assertIn('yichen-content-archive',result['backend'])
            self.assertFalse(result['discovery_performed'])


class CalibrationTests(unittest.TestCase):
    def fixture(self,root):
        generated=root/'generated'; generated.mkdir()
        places=json.loads((ROOT/'examples/places.json').read_text())
        reviews=json.loads((ROOT/'examples/review-items.json').read_text())
        paths={key:generated/name for key,name in [('PLACES_PATH','places-data.js'),('REVIEW_DATA_PATH','review-data.js'),('REVIEW_SEED_PATH','review-progress-seed.js'),('UNRESOLVED_PATH','pending.md')]}
        for key,variable,data in [('PLACES_PATH','PLACES_DATA',places),('REVIEW_DATA_PATH','PLACE_REVIEW_DATA',reviews),('REVIEW_SEED_PATH','PLACE_REVIEW_SEED',{})]:
            paths[key].write_text('window.'+variable+' = '+json.dumps(data,ensure_ascii=False)+';\n')
        return paths,places,reviews
    def test_unmentioned_rows_are_not_discarded(self):
        seed,count=calibration.build_seed({'results':[]},[{'id':'untouched'}],{})
        self.assertEqual(seed,{}); self.assertEqual(count,1)
    def test_all_wrong_and_failed_manual_address_stay_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); paths,_,items=self.fixture(root)
            export=root/'export.json'; export.write_text(json.dumps({'results':[{'id':items[0]['id'],'kind':'all_wrong'},{'id':items[1]['id'],'kind':'manual_address','address':'example address'}]}))
            with patch.multiple(calibration,ROOT=root,GEOCODE_CACHE_PATH=root/'cache.json',**paths),patch.object(sys,'argv',['apply',str(export)]),patch.dict(os.environ,{'AMAP_WEB_SERVICE_KEY':''}):
                calibration.main()
            remaining=calibration.load_js_assignment(paths['REVIEW_DATA_PATH'],'PLACE_REVIEW_DATA')
            self.assertEqual(len(remaining),2)
            seed=calibration.load_js_assignment(paths['REVIEW_SEED_PATH'],'PLACE_REVIEW_SEED')
            self.assertEqual(seed[items[1]['id']]['kind'],'all_wrong')
    def test_multiple_branches_tags_and_reapply(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); paths,places,items=self.fixture(root)
            export=root/'export.json'
            export.write_text(json.dumps({'results':[{'id':items[0]['id'],'kind':'candidates','name':items[0]['name'],'city':'北京','category':'咖啡','selectedCandidates':items[0]['candidates']}],'tagChanges':[{'id':places[0]['id'],'tags':['甜品','咖啡']}]}))
            with patch.multiple(calibration,ROOT=root,GEOCODE_CACHE_PATH=root/'cache.json',**paths),patch.object(sys,'argv',['apply',str(export)]):
                calibration.main(); first=paths['PLACES_PATH'].read_bytes(); calibration.main()
            self.assertEqual(paths['PLACES_PATH'].read_bytes(),first)
            self.assertEqual(len(calibration.load_js_assignment(paths['PLACES_PATH'],'PLACES_DATA')),6)
            self.assertEqual(len(calibration.load_js_assignment(paths['REVIEW_DATA_PATH'],'PLACE_REVIEW_DATA')),1)
    def test_date_suffix_metadata_and_unknown_city(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); raw=root/'raw';raw.mkdir()
            (raw/'2000-1-1_update-2.md').write_text('- 示例小店：示例菜\n')
            metadata=root/'metadata.json';metadata.write_text(json.dumps({'2000-1-1_update-2.md':{'示例小店':{'city':'','category':'小店'}}}))
            with patch.multiple(build_places,RAW_DIR=raw,RAW_UPDATE_METADATA_PATH=metadata):
                automatic,manual=build_places.parse_markdown_files()
            self.assertEqual(len(automatic),0);self.assertEqual(manual[0].recommended_food,['示例菜'])
    def test_export_audit_rejects_private_paths_and_token_shapes(self):
        self.assertIn('runtime/private file',audit_public.inspect('data/reviews.sqlite3',b''))
        self.assertIn('GitHub credential',audit_public.inspect('bad.txt',('ghp_'+'x'*36).encode()))

    def test_rebuild_preserves_all_aliases_provenance_and_calibrated_tags(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); paths,places,_=self.fixture(root)
            source=copy.deepcopy(places[0])
            source.update(savedName='示例新增别名',savedNames=['示例新增别名','示例第二别名'],tags=['美食'],category='美食',sourceIds=['example:another-source'])
            paths['REVIEW_SEED_PATH'].write_text('window.PLACE_REVIEW_SEED = '+json.dumps({'tag:'+places[0]['id']:{'kind':'tags','tags':places[0]['tags']}})+';\n')
            with patch.multiple(build_places,ROOT=root,GENERATED_DIR=root/'generated',**paths):
                build_places.write_outputs([source],[],{})
            updated=calibration.load_js_assignment(paths['PLACES_PATH'],'PLACES_DATA')
            self.assertEqual(len(updated),4)
            place=next(p for p in updated if p['id']==places[0]['id'])
            self.assertIn('示例第二别名',place['savedNames'])
            self.assertEqual(place['tags'],places[0]['tags'])
            self.assertIn('example:another-source',place['sourceIds'])


if __name__=='__main__': unittest.main()
