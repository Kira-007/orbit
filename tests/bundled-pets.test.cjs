const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{fileURLToPath}=require('node:url');
const {bundledPets}=require('../src/main/bundled-pets.cjs');
test('bundled sheets resolve from a relocated checkout, including spaces',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'orbit moved '));
 try{fs.cpSync(path.join(__dirname,'../assets'),path.join(root,'assets'),{recursive:true});const pets=bundledPets(root);assert.equal(pets.length,1);for(const sheet of Object.values(pets[0].spriteSheets)){const file=fileURLToPath(sheet.sheet);assert.ok(file.startsWith(root+path.sep));assert.ok(fs.existsSync(file));}}
 finally{fs.rmSync(root,{recursive:true,force:true});}
});
