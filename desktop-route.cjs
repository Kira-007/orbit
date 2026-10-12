function desktopMessageUrl(thread,prompt){
 if(typeof thread!=='string'||!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(thread))throw Error('Invalid Desktop thread');
 const url=new URL('codex://threads/'+thread);url.searchParams.set('prompt',prompt);return url.href;
}
module.exports={desktopMessageUrl};
