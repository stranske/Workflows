const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(__dirname+'/retention-functions.js','utf8');
const cases=[[14,7,7],[30,7,7],[14,90,14],[30,90,30],[14,1,1],[30,1,1]];
for(const [requested,limit,expected] of cases){
 const warnings=[], env={GITHUB_RETENTION_DAYS:String(limit)};
 const context={process:{env},warning:m=>warnings.push(m),Timestamp:{fromDate:d=>d},Date};
 vm.createContext(context);vm.runInContext(source,context);
 const start=new Date(), expiry=context.getExpiration(requested);
 const days=Math.round((expiry-start)/86400000);assert.strictEqual(days,expected);
 assert.strictEqual(warnings.length,requested>limit?1:0);
 console.log(JSON.stringify({requested,limit,effective_days:days,warnings:warnings.length,result:'PASS'}));
}
