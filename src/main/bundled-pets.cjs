const fs=require('node:fs'),path=require('node:path'),{pathToFileURL}=require('node:url');
function bundledPets(root=path.resolve(__dirname,'../..')){
 return JSON.parse(fs.readFileSync(path.join(root,'assets/library/pets.json'),'utf8')).map(pet=>({...pet,spriteSheets:Object.fromEntries(Object.entries(pet.spriteSheets).map(([state,config])=>[state,{...config,sheet:pathToFileURL(path.join(root,config.sheet)).href}]))}));
}
module.exports={bundledPets};
