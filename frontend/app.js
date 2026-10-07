const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
let data=null, days=7, selectedFile=null, deferredInstall=null;

// Demo workspace data is intentionally event-driven: the forecast is rebuilt from
// today's cash plus dated expected inflows/outflows, rather than a decorative curve.
const fallbackEvents=[
  [3,-6200,'Supplier invoice','out'],
  [7,-9500,'Payroll','out'],
  [11,-6800,'Rent and utilities','out'],
  [15,-8450,'Stock purchase','out'],
  [19,-6500,'Quarterly tax instalment','out'],
  [22,12000,'Customer payment','in'],
  [26,10000,'Customer payment','in'],
  [29,9800,'Customer payment','in']
];
function buildBalances(start,events){
  const out=[Number(start)||0];
  for(let d=1;d<=30;d++) out.push(out[d-1]+events.filter(e=>e[0]===d).reduce((s,e)=>s+Number(e[1]),0));
  return out;
}
const fallback={start:48600,events:fallbackEvents,signals:[
  {type:'warn',title:'Balance drops below buffer',text:'Expected around day 12.',amount:''},
  {type:'tax',title:'Equipment purchase',text:'Possible capital allowance signal',amount:'RM 2,400'},
  {type:'tax',title:'Software subscriptions',text:'Possible digital expense signal',amount:'RM 860'}
],documents:[
  {title:'bank-statement-sep.csv',text:'Analysed 128 transactions'},
  {title:'invoice-1042.pdf',text:'Stored for review'}
]};
fallback.balances=buildBalances(fallback.start,fallback.events);
fallback.signals[0].text='Expected around day '+fallback.balances.findIndex(v=>v<15000)+'.';

function money(n){return 'RM '+Math.round(Number(n)||0).toLocaleString('en-MY')}
// Escape any text that originates from uploaded files before it is put in innerHTML.
function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function normalise(x){
  const base=x&&Array.isArray(x.balances)?x:fallback;
  if(!Array.isArray(base.events)) base.events=fallbackEvents;
  if(!Array.isArray(base.balances)||base.balances.length!==31) base.balances=buildBalances(base.start,base.events);
  return base;
}
function toast(msg){const el=$('#toast');el.textContent=msg;el.classList.add('show');clearTimeout(window._toast);window._toast=setTimeout(()=>el.classList.remove('show'),2400)}

function svgChart(values, cls='', opts={}){
  const w=700,h=230,p={l:22,r:18,t:18,b:30};
  const buffer=opts.buffer!=null?Number(opts.buffer):null;
  const minData=Math.min(...values);
  const maxData=Math.max(...values);
  // Scale to the actual selected forecast window. Only include the safety
  // buffer when it is relevant; do not force RM 0 into every chart.
  const domainMin=Math.min(minData,buffer==null?minData:buffer);
  const domainMax=Math.max(maxData,buffer==null?maxData:buffer);
  const pad=Math.max(1800,(domainMax-domainMin)*0.09);
  const lo=domainMin-pad, hi=domainMax+pad, range=Math.max(1,hi-lo);
  const x=i=>p.l+i*(w-p.l-p.r)/Math.max(1,values.length-1);
  const y=v=>h-p.b-(v-lo)/range*(h-p.t-p.b);
  const pts=values.map((v,i)=>[x(i),y(v)]);
  const line=pts.map((pt,i)=>(i?'L':'M')+pt[0].toFixed(1)+' '+pt[1].toFixed(1)).join(' ');
  const baseY=h-p.b;
  const area=line+' L '+pts.at(-1)[0].toFixed(1)+' '+baseY+' L '+pts[0][0].toFixed(1)+' '+baseY+' Z';
  const low=Math.min(...values), li=values.indexOf(low), last=pts.at(-1);
  const bufferLine=buffer!=null&&buffer>=lo&&buffer<=hi
    ? `<line class="buffer-line" x1="${p.l}" x2="${w-p.r}" y1="${y(buffer)}" y2="${y(buffer)}"/><text class="buffer-label" x="${p.l+4}" y="${Math.max(12,y(buffer)-7)}">Buffer ${money(buffer)}</text>` : '';
  const lowLabel=opts.showLow!==false
    ? (()=>{
        const nearRight=pts[li][0]>w-145;
        const labelX=nearRight?Math.max(p.l,pts[li][0]-112):Math.min(pts[li][0]+10,w-112);
        const labelY=Math.max(pts[li][1]-14,18);
        return `<g class="low-mark"><circle cx="${pts[li][0]}" cy="${pts[li][1]}" r="6"/><text x="${labelX}" y="${labelY}">Low ${money(low)}</text></g>`;
      })() : '';
  // If the selected window ends at its lowest point, an end-value label would
  // sit on top of the low marker. The low label is the useful one in that case.
  const endLabel=opts.showEnd!==false && li!==values.length-1
    ? `<text class="end-label" x="${Math.max(p.l,last[0]-70)}" y="${Math.max(last[1]-10,18)}">${money(values.at(-1))}</text>` : '';
  const labels=values.length<=8
    ? values.map((_,i)=>`<text class="x-label" x="${x(i)}" y="${h-7}" text-anchor="middle">${i===0?'Today':'Day '+i}</text>`).join('')
    : `<text class="x-label" x="${p.l}" y="${h-7}">Today</text><text class="x-label" x="${x(values.length-1)}" y="${h-7}" text-anchor="end">Day ${values.length-1}</text>`;
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" class="${cls}" role="img" aria-label="Cash balance forecast"><path class="chart-grid" d="M${p.l} ${y((hi+lo)*.75)}H${w-p.r}M${p.l} ${y((hi+lo)*.5)}H${w-p.r}M${p.l} ${y((hi+lo)*.25)}H${w-p.r}"/><path class="chart-area" d="${area}"/><path class="chart-line" d="${line}"/>${bufferLine}${lowLabel}${endLabel}${labels}</svg>`;
}

function render(){
  data=normalise(data);
  const low=Math.min(...data.balances),li=data.balances.indexOf(low);
  $('#cashValue').textContent=money(data.start);
  $('#lowBalance').textContent=money(low);
  const firstBelow=data.balances.findIndex(v=>v<15000); const gap=Math.max(0,15000-low); $('#gapDay').textContent=firstBelow>0?'Day '+firstBelow:'No gap'; $('#gapValue').textContent=money(gap);
  $('#attentionTitle').textContent=low<15000?'Potential cash gap ahead':'Cash position looks healthy';
  $('#attentionText').textContent=low<15000?`Projected balance may fall below the RM 15,000 buffer around day ${Math.max(1,firstBelow)}.`:'Your projected balance stays above the cash buffer.';
  $('#cashStatus').textContent=low<15000?'Watch your next payments':'Healthy today'; $('#lowPill').textContent=low<15000?'Watch':'Healthy'; $('#lowPill').className='pill '+(low<15000?'warn':'ok');
  $('#miniChart').innerHTML=svgChart(data.balances,'mini-svg',{buffer:15000,showLow:false,showEnd:false});
  drawLarge(days);renderEvents();renderDocs();renderSignals();renderActivity();
  const nGap=$('#notifGapText'); if(nGap) nGap.textContent=low<15000?`Your projected balance may fall below the buffer around day ${Math.max(1,firstBelow)}.`:'Your projected balance stays above the cash buffer.';
  $('#signalCount').textContent=(data.signals||[]).filter(x=>x.type==='tax').length;
  $('#docCount').textContent=(data.documents||[]).length;
}
function drawLarge(n){
  const vals=data.balances.slice(0,n+1);
  const low=Math.min(...vals);
  const lowDay=vals.indexOf(low);
  const below=vals.findIndex(v=>v<15000);
  $('#lowBalance').textContent=money(low);
  $('#lowPill').textContent=low<15000?'Watch':'Healthy';
  $('#lowPill').className='pill '+(low<15000?'warn':'ok');
  $('#largeChart').innerHTML=svgChart(vals,'large-svg',{buffer:15000});
  const note=document.getElementById('forecastNote');
  if(note) note.textContent=low<15000
    ? `Lowest projected balance is ${money(low)} on day ${lowDay}. The RM 15,000 buffer is crossed on day ${below>0?below:'—'}.`
    : `Lowest projected balance is ${money(low)} within the selected ${n}-day window.`;
  const evIn=data.events.filter(e=>e[3]==='in'&&e[0]<=n).reduce((a,e)=>a+Math.abs(e[1]),0);
  const evOut=data.events.filter(e=>e[3]==='out'&&e[0]<=n).reduce((a,e)=>a+Math.abs(e[1]),0);
  $('#inflowMetric').textContent=money(evIn);$('#outflowMetric').textContent=money(evOut);
}
function renderEvents(){
  const items=data.events.map(e=>`<div class="event-item"><span class="date">DAY ${e[0]}</span><div style="flex:1"><b>${esc(e[2])}</b><small>${e[3]==='in'?'Expected money in':'Expected money out'}</small></div><span class="amount ${e[3]}">${e[3]==='in'?'+':'−'}${money(Math.abs(e[1]))}</span></div>`).join('');
  $('#eventList').innerHTML=items;
}
function renderDocs(filter='all'){
  let docs=(data.documents||[]).map(d=>({...d,type:d.title.toLowerCase().includes('statement')?'statement':d.title.toLowerCase().includes('invoice')?'invoice':'receipt',icon:esc(d.title.split('.').pop().toUpperCase().slice(0,4))}));
  if(filter!=='all')docs=docs.filter(d=>d.type===filter);
  $('#documentList').innerHTML=docs.map(d=>`<div class="doc-item"><span class="doc-icon ${d.type}">${d.icon}</span><div class="doc-meta"><b>${esc(d.title)}</b><small>${esc(d.text)}</small></div><span>›</span></div>`).join('')||'<div class="white-card"><small class="muted">No documents in this filter yet.</small></div>';
}
function renderSignals(){const s=(data.signals||[]).filter(x=>x.type==='tax');$('#signalList').innerHTML=s.map(x=>`<div class="signal-item"><span class="signal-mark">✓</span><div class="signal-copy"><b>${esc(x.title)}</b><small>${esc(x.text)}</small></div><span class="signal-amount">${esc(x.amount||'Review')}</span></div>`).join('')}
function renderActivity(){
  const evHtml=data.events.slice(0,3).map(e=>`<div class="activity-item"><span class="activity-icon">${e[3]==='in'?'↗':'↘'}</span><div><b>${esc(e[2])}</b><small>Day ${e[0]} · ${e[3]==='in'?'Expected inflow':'Expected outflow'}</small></div><span class="amount ${e[3]}">${e[3]==='in'?'+':'−'}${money(Math.abs(e[1]))}</span></div>`).join('');
  $('#homeActivity').innerHTML=evHtml || '<div class="white-card"><small class="muted">No recent activity.</small></div>';
}
function go(screen){
  $$('.screen').forEach(s=>s.classList.toggle('active',s.dataset.screen===screen));
  $$('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.nav===screen));
  document.body.classList.toggle('screen-wide',screen==='cashflow');
  window.scrollTo({top:0,behavior:'smooth'});
}
function openSheet(id){$('#sheetBackdrop').classList.add('show');$('#'+id).classList.add('open');$('#'+id).setAttribute('aria-hidden','false');$('#fab').classList.add('open')}
function closeSheet(id){$('#'+id).classList.remove('open');$('#'+id).setAttribute('aria-hidden','true');if(!$$('.sheet.open').length){$('#sheetBackdrop').classList.remove('show');$('#fab').classList.remove('open')}}
async function load(){try{const r=await fetch('/api/dashboard',{cache:'no-store'});if(r.ok)data=await r.json()}catch(e){}render()}

const hr=new Date().getHours();$('#greeting').textContent=(hr<12?'Good morning':hr<18?'Good afternoon':'Good evening');$('#todayLabel').textContent=new Date().toLocaleDateString('en-MY',{weekday:'long',day:'numeric',month:'short'}).toUpperCase();
$$('[data-nav]').forEach(b=>b.onclick=()=>go(b.dataset.nav));
$$('[data-action]').forEach(b=>b.onclick=()=>{const a=b.dataset.action;if(a==='upload')openSheet('uploadSheet');else go(a==='forecast'?'cashflow':a)});
$('#fab').onclick=()=>openSheet('uploadSheet');$('#attentionBtn').onclick=()=>go('cashflow');$('#bellBtn').onclick=()=>openSheet('notifySheet');
$('#refreshBtn').onclick=async()=>{await load();toast('Cash forecast refreshed')};$('#profileBtn').onclick=()=>go('more');$('#seeAllBtn').onclick=()=>go('more');
$$('[data-close]').forEach(b=>b.onclick=()=>closeSheet(b.dataset.close));$('#sheetBackdrop').onclick=()=>$$('.sheet.open').forEach(s=>closeSheet(s.id));
$$('.segmented button').forEach(b=>b.onclick=()=>{$$('.segmented button').forEach(x=>x.classList.remove('active'));b.classList.add('active');days=+b.dataset.days;drawLarge(days)});
$$('.filter').forEach(b=>b.onclick=()=>{$$('.filter').forEach(x=>x.classList.remove('active'));b.classList.add('active');renderDocs(b.dataset.filter)});
$('#fileInput').onchange=e=>{selectedFile=e.target.files[0]||null;$('#selectedFile').textContent=selectedFile?selectedFile.name:'No file selected';$('#fileLabel').textContent=selectedFile?selectedFile.name:'Choose a file'};
$('#uploadSubmit').onclick=async()=>{if(!selectedFile){$('#uploadMessage').textContent='Choose a file first.';return}const fd=new FormData();fd.append('file',selectedFile);$('#uploadMessage').textContent='Analysing…';try{const r=await fetch('/api/upload',{method:'POST',body:fd});const j=await r.json();if(!r.ok)throw new Error(j.detail||'Upload failed');data=j.dashboard;render();$('#uploadMessage').textContent=j.message||'Analysis complete.';toast('Document analysed');setTimeout(()=>closeSheet('uploadSheet'),700)}catch(e){$('#uploadMessage').textContent=e.message}};
$('#reportBtn').onclick=async()=>{openSheet('reportSheet');$('#reportBody').innerHTML='<p class="muted">Loading report…</p>';try{const r=await fetch('/api/tax-report');const j=await r.json();$('#reportBody').innerHTML=(j.items||[]).map(x=>`<div class="report-row"><b>${esc(x.title)}</b><small>${esc(x.text||x.description||'Review supporting documents and eligibility.')}</small></div>`).join('')||'<div class="report-row"><b>No report items yet</b><small>Upload invoices or receipts to create signals.</small></div>'}catch(e){$('#reportBody').innerHTML='<div class="report-row"><b>Report unavailable</b><small>Please try again.</small></div>'}};
$('#referralBtn').onclick=async()=>{if(!$('#consent').checked){toast('Please give consent before requesting a referral');return}$('#referralBtn').disabled=true;try{const r=await fetch('/api/referral',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({consent:true})});const j=await r.json();if(!r.ok)throw new Error(j.detail||'Request failed');toast('Referral request submitted');$('#referralBtn').textContent='Referral submitted'}catch(e){toast(e.message)}finally{$('#referralBtn').disabled=false}};
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();deferredInstall=e});$('#installBtn').onclick=async()=>{if(deferredInstall){deferredInstall.prompt();await deferredInstall.userChoice;deferredInstall=null}else toast('Use your browser menu to add Finvia to your home screen')};$('#aboutBtn').onclick=()=>toast('Finvia prototype · SME cash, tax signals and financing referral');
if('serviceWorker' in navigator)navigator.serviceWorker.register('/service-worker.js').catch(()=>{});load();
