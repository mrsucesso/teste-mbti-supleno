import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestFase10K(unittest.TestCase):
    def test_adapter_accepts_frontend_product_alias_and_styles_object(self):
        script = r'''
const fs=require('fs'),vm=require('vm'); const c={}; c.globalThis=c;
vm.runInNewContext(fs.readFileSync('assets/integracao-v1-adapter.js','utf8'),c);
for (const [teste, resultado] of [['tipos',{code:'INTJ',gender:'M'}],['estilos','D'],['tracos',{SO:{sum:15,percent:50,faixa:'medio'},AN:{sum:15,percent:50,faixa:'medio'},OM:{sum:15,percent:50,faixa:'medio'},TE:{sum:15,percent:50,faixa:'medio'},CO:{sum:15,percent:50,faixa:'medio'}}]]) {
 const out=c.adaptarCapturaV1({teste,resultado,submission_id:teste,name:'Pessoa',email:'pessoa@example.invalid',consentimento:true});
 if(out.product!==teste || typeof out.result!=='object' || out.contract!=='supleno.integracao.v1') throw Error(teste);
}
'''
        subprocess.run(['node', '-e', script], cwd=ROOT, check=True)

    def test_progress_validates_tipos_and_estilos_semantics(self):
        script = r'''
const fs=require('fs'),vm=require('vm'); const c={Date,JSON,Number,Object,Array,localStorage:null}; c.globalThis=c;
vm.runInNewContext(fs.readFileSync('assets/progresso-local.js','utf8'),c); const p=c.SuplenoProgresso;
const tipos={respostas:Array(28).fill('E'),progresso:28,ordem:Array.from({length:28},(_,i)=>i),resultado:{code:'ENFP',gender:'M'}};
if(p.salvar('tipos',tipos)!==null) throw Error('tipos inconsistente aceito');
const estilos={respostas:['D','D','I','I'],progresso:4,ordem:[0,1,2,3],resultado:{code:'S'}};
if(p.salvar('estilos',estilos)!==null) throw Error('estilos inconsistente aceito');
'''
        subprocess.run(['node', '-e', script], cwd=ROOT, check=True)

    def test_frontends_use_v1_status_and_clipboard_rejection_fallback(self):
        for product in ('tipos', 'estilos', 'tracos'):
            text=(ROOT/product/'index.html').read_text()
            self.assertIn("data.status", text)
            self.assertNotIn("data.ok === true", text)
        share=(ROOT/'assets/compartilhamento.js').read_text()
        self.assertIn('.catch(function', share)
        mapa=(ROOT/'mapa/index.html').read_text()
        self.assertIn('.catch(function', mapa)

    def test_apps_script_mentions_and_consumes_v1_fields(self):
        text=(ROOT/'apps-script/Code.gs').read_text()
        for token in ('supleno.integracao.v1','data.product','data.person','data.result','data.scores','data.consent'):
            self.assertIn(token,text)


if __name__ == '__main__':
    unittest.main()
