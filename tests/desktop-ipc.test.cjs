const test=require('node:test'),assert=require('node:assert/strict');const {discoverOwner,sendDesktopMessage}=require('../src/main/desktop-ipc.cjs');
test('Desktop submission targets the confirmed owner and preserves thread permissions',async()=>{const calls=[];let closed=false;const client={request:async(method,params,options)=>{calls.push({method,params,options});return method==='thread-owner-discovery'?{resultType:'success',handledByClientId:'desktop-owner',result:{supportsUntrustedAppInput:true}}:{resultType:'success',result:{accepted:true}};},close:()=>closed=true};await sendDesktopMessage('thread','user message',async()=>client);assert.equal(calls.length,2);assert.equal(calls[1].method,'thread-follower-start-turn');assert.equal(calls[1].options.targetClientId,'desktop-owner');assert.equal(calls[1].params.turnStart.request.input[0].text,'user message');assert.equal(calls[1].params.turnStart.context.inheritThreadSettings,true);assert.equal(closed,true);});
test('unsupported external input is refused',async()=>{await assert.rejects(discoverOwner({request:async()=>({resultType:'success',handledByClientId:'desktop',result:{supportsUntrustedAppInput:false}})},'thread'),/cannot accept/);});
test('Desktop turn identifies the target thread and a unique user message',async()=>{
 const messages=[];const client={request:async(method,params)=>{
  if(method==='thread-owner-discovery')return{resultType:'success',handledByClientId:'desktop',result:{supportsUntrustedAppInput:true}};
  const request=params.turnStart.request;
  if(request.threadId!==params.conversationId)return{resultType:'error',error:'Turn request thread does not match the conversation'};
  messages.push(request.clientUserMessageId);return{resultType:'success',result:{accepted:true}};
 },close:()=>{}};
 await sendDesktopMessage('selected-thread','first',async()=>client);
 await sendDesktopMessage('selected-thread','second',async()=>client);
 assert.equal(messages.length,2);assert.match(messages[0],/^[0-9a-f-]{36}$/);assert.notEqual(messages[0],messages[1]);
});
test('ambiguous submission failure is never retried',async()=>{let submits=0;const client={request:async(method)=>{if(method==='thread-owner-discovery')return{resultType:'success',handledByClientId:'desktop',result:{supportsUntrustedAppInput:true}};submits++;throw Error('Check the thread before retrying');},close:()=>{}};await assert.rejects(sendDesktopMessage('thread','message',async()=>client));assert.equal(submits,1);});
