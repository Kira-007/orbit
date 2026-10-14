const {test}=require('node:test'),assert=require('node:assert/strict');
const {petState}=require('../src/renderer/pet-state.js');
test('abandoned stale task does not override idle or current work',()=>{const old={status:'unknown',time:1};assert.equal(petState([old],1000000),'idle');assert.equal(petState([old,{status:'working',time:1000000}],1000000),'working');assert.equal(petState([old,{status:'done',time:999999}],1000000),'done');assert.equal(petState([{status:'error',time:1}],1000000),'idle');});
