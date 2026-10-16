// Shared native-output comparison for parity tests and benchmarks.
export function compare(actual, expected) {
  const diffs=[];
  const metrics={ maxCoordinateDelta:0, maxConfidenceDelta:0, exact:true };
  function walk(a,b,path) {
    if (path.endsWith('.timings')) return;
    // Backend accumulation order can affect last bits; public confidences and
    // geometry have explicit tolerances, all text/labels/order must match exactly.
    if (typeof a==='number'&&typeof b==='number') {
      const coordinate=/\.(box|bbox)\.\d+$/.test(path);
      const confidence=path.endsWith('.conf');
      const delta=Math.abs(a-b);
      if(delta)metrics.exact=false;
      if(coordinate)metrics.maxCoordinateDelta=Math.max(metrics.maxCoordinateDelta,delta);
      if(confidence)metrics.maxConfidenceDelta=Math.max(metrics.maxConfidenceDelta,delta);
      const tolerance=confidence?0.0002:coordinate?0.11:0.00001;
      if (Math.abs(a-b)>tolerance) diffs.push({path,actual:a,expected:b});
    } else if (a===null||b===null||typeof a!=='object'||typeof b!=='object') {
      if (a!==b) diffs.push({path,actual:a,expected:b});
    } else {
      if (Array.isArray(a)&&a.length!==b.length) diffs.push({path:path+'.length',actual:a.length,expected:b.length});
      for(const k of new Set([...Object.keys(a),...Object.keys(b)])) walk(a[k],b[k],path+'.'+k);
    }
  }
  walk(actual,expected,'pages'); return {differences:diffs,metrics};
}
