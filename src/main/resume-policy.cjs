function inactiveQueueError(error,text=''){
 if(!error||error.killed||error.signal)return false;
 return /(?:thread|session|conversation).{0,100}(?:not (?:loaded|running|active|open)|is (?:closed|inactive)|must be (?:loaded|resumed))|(?:not (?:loaded|running|active|open)|closed|inactive).{0,100}(?:thread|session|conversation)/i.test(text);
}
module.exports={inactiveQueueError};
