/* Opening page: same animation as the website. Plays once per browser session. */
(function(){
  var intro=document.getElementById('intro'),root=document.documentElement;
  if(!intro)return;
  if(matchMedia('(prefers-reduced-motion:reduce)').matches){intro.remove();return}
  try{sessionStorage.setItem('finviaIntro','1')}catch(e){}
  root.classList.add('lock');
  var tm=setTimeout(function(){root.classList.remove('lock')},3000);
  intro.addEventListener('animationend',function(e){if(e.target===intro&&e.animationName==='introOut'){intro.remove();root.classList.remove('lock')}});
  function skip(){clearTimeout(tm);intro.classList.add('skip');setTimeout(function(){root.classList.remove('lock')},260)}
  intro.addEventListener('click',skip);
  addEventListener('keydown',function(e){if(e.key==='Escape'&&document.getElementById('intro'))skip()});
})();
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
let data=null, days=7, selectedFile=null, deferredInstall=null;

/* ---------- Offline fallback (used only if the API cannot be reached) ---------- */
const fallbackEvents=[
  [3,-6200,'Supplier invoice','out'],[7,-9500,'Payroll','out'],[11,-6800,'Rent and utilities','out'],
  [15,-8450,'Stock purchase','out'],[19,-6500,'Quarterly tax instalment','out'],
  [22,12000,'Customer payment','in'],[26,10000,'Customer payment','in'],[29,9800,'Customer payment','in']
];
function buildBalances(start,events){const o=[Number(start)||0];for(let d=1;d<=30;d++)o.push(o[d-1]+events.filter(e=>e[0]===d).reduce((s,e)=>s+Number(e[1]),0));return o}
function makeFallback(){
  const bal=buildBalances(48600,fallbackEvents), mk=n=>{const v=bal.slice(0,n+1),low=Math.min(...v);
    const inn=fallbackEvents.filter(e=>e[0]<=n&&e[1]>0).reduce((a,e)=>a+e[1],0),out=-fallbackEvents.filter(e=>e[0]<=n&&e[1]<0).reduce((a,e)=>a+e[1],0);
    return {days:n,low,low_day:v.indexOf(low),end:v.at(-1),net:v.at(-1)-v[0],inflow:inn,outflow:out,first_below:v.findIndex(x=>x<15000)>=0?v.findIndex(x=>x<15000):null}};
  return {start:48600,buffer:15000,as_of:new Date().toISOString().slice(0,10),demo:true,balances:bal,
    band_low:bal.map((v,i)=>v-1500-i*120),band_high:bal.map((v,i)=>v+1500+i*120),events:fallbackEvents,
    windows:{7:mk(7),14:mk(14),30:mk(30)},
    cash:{avg_daily_in:1050,avg_daily_out:1750,runway_days:27,safe_to_spend:33600,categories:[],recent:[],history:[]},
    signals:[{type:'tax',title:'Equipment purchase',text:'Possible capital allowance signal',amount:'RM 2,400'},{type:'tax',title:'Software subscriptions',text:'Possible digital expense signal',amount:'RM 860'}],
    documents:[{title:'bank-statement-sep.csv',text:'Analysed 128 transactions'},{title:'invoice-1042.pdf',text:'Stored for review'}]};
}

/* ---------- Helpers ---------- */
const money=n=>'RM '+Math.round(Number(n)||0).toLocaleString('en-MY');
const signed=n=>(n>=0?'+':'−')+money(Math.abs(n));
const compact=n=>{const a=Math.abs(n),s=n<0?'−':'';return a>=1e6?s+(a/1e6).toFixed(1)+'M':a>=1e4?s+Math.round(a/1e3)+'k':a>=1e3?s+(a/1e3).toFixed(1)+'k':s+Math.round(a)};
function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function toast(msg){const el=$('#toast');el.textContent=msg;el.classList.add('show');clearTimeout(window._toast);window._toast=setTimeout(()=>el.classList.remove('show'),2600)}
const anchor=()=>{const d=new Date((data&&data.as_of?data.as_of:new Date().toISOString()).slice(0,10)+'T00:00:00');return isNaN(d)?new Date():d};
const dayDate=i=>{const d=anchor();d.setDate(d.getDate()+i);return d};
const fmtDate=(d,o={day:'numeric',month:'short'})=>d.toLocaleDateString('en-MY',o);
const fmtDay=i=>i===0?'Today':fmtDate(dayDate(i));
const buf=()=>Number(data.buffer)||15000;

function normalise(x){
  if(!x||!Array.isArray(x.balances)||x.balances.length!==31) x=makeFallback();
  if(!Array.isArray(x.events)) x.events=[];
  if(!x.windows) x.windows=makeFallback().windows;
  if(!x.cash) x.cash=makeFallback().cash;
  if(!Array.isArray(x.band_low)||x.band_low.length!==31){x.band_low=x.balances;x.band_high=x.balances}
  return x;
}

/* ---------- Charts ---------- */
function miniChart(values,buffer){
  const w=700,h=120,p=6,lo=Math.min(...values,buffer)-1500,hi=Math.max(...values,buffer)+1500,r=hi-lo||1;
  const x=i=>p+i*(w-2*p)/(values.length-1),y=v=>h-p-(v-lo)/r*(h-2*p);
  const line=values.map((v,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)).join(' ');
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" class="mini-svg"><path class="chart-area" d="${line} L ${x(values.length-1)} ${h} L ${x(0)} ${h} Z"/><line class="buffer-line" x1="${p}" x2="${w-p}" y1="${y(buffer)}" y2="${y(buffer)}"/><path class="chart-line" d="${line}"/></svg>`;
}

/* Interactive forecast chart. Sized to its container so text stays crisp on phone and laptop. */
let chartState=null;
function drawLargeChart(n){
  const box=$('#largeChart'); if(!box) return;
  const W=Math.max(280,box.clientWidth||320), H=W>620?320:260;
  const pad={l:W>620?58:48,r:14,t:16,b:30};
  const vals=data.balances.slice(0,n+1), lo0=data.band_low.slice(0,n+1), hi0=data.band_high.slice(0,n+1), B=buf();
  // Only stretch the axis down to the buffer when it is close enough to matter;
  // otherwise the real forecast gets squashed against the top of the chart.
  const vmin=Math.min(...vals,...lo0), vmax=Math.max(...vals,...hi0), vspan=Math.max(vmax-vmin,vmax*.15,1);
  const showBuf=B>=vmin-vspan*.8&&B<=vmax+vspan*.8;
  const dmin=showBuf?Math.min(vmin,B):vmin, dmax=showBuf?Math.max(vmax,B):vmax, span=Math.max(dmax-dmin,1), padv=span*.1;
  const lo=dmin-padv, hi=dmax+padv;
  const x=i=>pad.l+i*(W-pad.l-pad.r)/Math.max(1,n), y=v=>H-pad.b-(v-lo)/(hi-lo)*(H-pad.t-pad.b);
  const path=a=>a.map((v,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)).join(' ');
  const line=path(vals), base=H-pad.b;
  const area=`${line} L ${x(n)} ${base} L ${x(0)} ${base} Z`;
  const band=`${path(hi0)} ${lo0.map((v,i)=>`L ${x(n-i).toFixed(1)} ${y(lo0[n-i]).toFixed(1)}`).join(' ')} Z`;
  const ticks=[0,.25,.5,.75,1].map(t=>lo+(hi-lo)*t);
  const grid=ticks.map(v=>`<line class="g" x1="${pad.l}" x2="${W-pad.r}" y1="${y(v)}" y2="${y(v)}"/><text class="yl" x="${pad.l-8}" y="${y(v)+3.5}" text-anchor="end">${compact(v)}</text>`).join('');
  const maxLab=Math.max(2,Math.floor((W-pad.l-pad.r)/74)), step=[1,2,3,5,7,10,15].find(s=>Math.ceil(n/s)+1<=maxLab)||15, xl=[];
  for(let i=0;i<=n;i+=step) xl.push(i); if(xl[xl.length-1]!==n){ if(n-xl[xl.length-1]>=step*.6) xl.push(n); else xl[xl.length-1]=n; }
  const xlab=xl.map(i=>`<text class="xl" x="${x(i)}" y="${H-9}" text-anchor="${i===0?'start':i===n?'end':'middle'}">${i===0?'Today':fmtDate(dayDate(i))}</text>`).join('');
  const low=Math.min(...vals), li=vals.indexOf(low);
  const marks=data.events.filter(e=>e[0]<=n).map(e=>`<circle class="ev ${e[3]}" cx="${x(e[0])}" cy="${y(vals[e[0]])}" r="4.5"/>`).join('');
  const bufY=y(B);
  const lowTx=Math.min(Math.max(x(li),pad.l+50),W-pad.r-50);
  const svg=`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Projected cash balance for the next ${n} days">
    <defs><linearGradient id="gArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2f7bff" stop-opacity=".22"/><stop offset="1" stop-color="#2f7bff" stop-opacity="0"/></linearGradient></defs>
    ${grid}<path class="band" d="${band}"/><path class="area" d="${area}"/>
    ${showBuf?`<line class="buf" x1="${pad.l}" x2="${W-pad.r}" y1="${bufY}" y2="${bufY}"/><text class="bl" x="${W-pad.r-2}" y="${bufY-6}" text-anchor="end">Buffer ${compact(B)}</text>`:''}
    <path class="ln" d="${line}"/>${marks}
    <g class="lowm"><circle cx="${x(li)}" cy="${y(low)}" r="6"/><text x="${lowTx}" y="${Math.min(y(low)+22,H-pad.b-6)}" text-anchor="middle">Low ${compact(low)}</text></g>
    ${xlab}
    <g class="cursor" style="display:none"><line class="cl" y1="${pad.t}" y2="${base}"/><circle class="cd" r="5.5"/></g>
    <rect class="hit" x="${pad.l}" y="0" width="${W-pad.l-pad.r}" height="${H}" fill="transparent"/></svg><div class="tip" role="status"></div>`;
  box.innerHTML=svg;
  chartState={n,x,y,vals,W,pad};
  const tip=box.querySelector('.tip'), cur=box.querySelector('.cursor'), hit=box.querySelector('.hit');
  const show=ev=>{
    const r=box.getBoundingClientRect(), px=(ev.clientX-r.left);
    const i=Math.max(0,Math.min(n,Math.round((px-pad.l)/((W-pad.l-pad.r)/n))));
    const cx=x(i), cy=y(vals[i]); cur.style.display='';
    cur.querySelector('.cl').setAttribute('x1',cx);cur.querySelector('.cl').setAttribute('x2',cx);
    cur.querySelector('.cd').setAttribute('cx',cx);cur.querySelector('.cd').setAttribute('cy',cy);
    const evs=data.events.filter(e=>e[0]===i);
    tip.innerHTML=`<b>${i===0?'Today':fmtDate(dayDate(i),{weekday:'short',day:'numeric',month:'short'})}</b><span>${money(vals[i])}</span>`+
      evs.map(e=>`<small class="${e[3]}">${e[3]==='in'?'+':'−'}${money(Math.abs(e[1]))} ${esc(e[2])}</small>`).join('')+
      (vals[i]<B?'<small class="out">Below buffer</small>':'');
    tip.style.display='block';
    const tw=tip.offsetWidth; tip.style.left=Math.max(4,Math.min(W-tw-4,cx-tw/2))+'px'; tip.style.top=Math.max(0,cy-tip.offsetHeight-14)+'px';
  };
  const hide=()=>{tip.style.display='none';cur.style.display='none'};
  hit.addEventListener('pointermove',show);hit.addEventListener('pointerdown',show);
  hit.addEventListener('pointerleave',hide);hit.addEventListener('pointerup',e=>{if(e.pointerType!=='mouse')setTimeout(hide,1800)});
}

function sparkline(values,h=120){
  const box=$('#csChart'); if(!box||!values.length) {if(box)box.innerHTML='';return}
  const W=Math.max(260,box.clientWidth||320), p=6, lo=Math.min(...values), hi=Math.max(...values), r=(hi-lo)||1;
  const x=i=>p+i*(W-2*p)/Math.max(1,values.length-1), y=v=>h-p-8-(v-lo)/r*(h-2*p-16);
  const line=values.map((v,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)).join(' ');
  box.innerHTML=`<svg viewBox="0 0 ${W} ${h}" width="${W}" height="${h}" aria-label="Cash balance, last ${values.length} days"><defs><linearGradient id="gCs" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2124a0" stop-opacity=".2"/><stop offset="1" stop-color="#2124a0" stop-opacity="0"/></linearGradient></defs><path d="${line} L ${x(values.length-1)} ${h-p} L ${x(0)} ${h-p} Z" fill="url(#gCs)"/><path d="${line}" fill="none" stroke="#2124a0" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${x(values.length-1)}" cy="${y(values.at(-1))}" r="5" fill="#2124a0" stroke="#fff" stroke-width="2.5"/></svg>`;
}

/* ---------- Render ---------- */
function render(){
  data=normalise(data);
  const B=buf(), w30=data.windows[30], low=w30.low, firstBelow=w30.first_below;
  $('#cashValue').textContent=money(data.start);
  $('#cashAsOf').textContent=data.demo?'Sample data':'As of '+fmtDate(anchor());
  $('#gapDay').textContent=firstBelow>0?'Day '+firstBelow:'No gap';
  $('#gapValue').textContent=money(Math.max(0,B-low));
  $$('.buffer-val').forEach(el=>el.textContent=money(B));
  const watch=low<B;
  $('#attentionTitle').textContent=watch?'Potential cash gap ahead':'Cash position looks healthy';
  $('#attentionText').textContent=watch?`Projected balance may fall below the ${money(B)} buffer around ${fmtDate(dayDate(Math.max(1,firstBelow)))} (day ${Math.max(1,firstBelow)}).`:'Your projected balance stays above the cash buffer for the next 30 days.';
  $('#cashStatus').textContent=watch?'Watch your next payments':'Healthy today';
  $('#miniChart').innerHTML=miniChart(data.balances,B);
  drawLarge(days);renderDocs();renderSignals();renderActivity();renderCash();
  const nGap=$('#notifGapText'); if(nGap) nGap.textContent=watch?`Your projected balance may fall below the buffer around day ${Math.max(1,firstBelow)}.`:'Your projected balance stays above the cash buffer.';
  $('#signalCount').textContent=(data.signals||[]).filter(x=>x.type==='tax').length;
  $('#docCount').textContent=(data.documents||[]).length;
}

function drawLarge(n){
  const wi=data.windows[n], B=buf(), vals=data.balances.slice(0,n+1);
  const watch=wi.low<B;
  $('#cfHeroLabel').textContent=`Projected balance on ${fmtDate(dayDate(n),{day:'numeric',month:'short'})}`;
  $('#cfHeroValue').textContent=money(wi.end);
  const d=$('#cfHeroDelta'); d.textContent=`${signed(wi.net)} vs today`; d.className='cf-delta '+(wi.net>=0?'pos':'neg');
  $('#lowPill').textContent=watch?'Watch':'Healthy'; $('#lowPill').className='pill '+(watch?'warn':'ok');
  drawLargeChart(n);
  $('#forecastNote').textContent=watch
    ? `Lowest projected balance is ${money(wi.low)} on ${fmtDate(dayDate(wi.low_day))}. It crosses the ${money(B)} buffer on day ${wi.first_below}. Tap or hover the chart for any day.`
    : `Lowest projected balance is ${money(wi.low)} on ${fmtDate(dayDate(wi.low_day))}, above your ${money(B)} buffer. Tap or hover the chart for any day.`;
  $('#inflowMetric').textContent=money(wi.inflow); $('#outflowMetric').textContent=money(wi.outflow);
  const nm=$('#netMetric'); nm.textContent=signed(wi.net); nm.className=wi.net>=0?'pos':'neg';
  $('#lowBalance').textContent=money(wi.low); $('#lowDayMetric').textContent=wi.low_day===0?'today':'on '+fmtDate(dayDate(wi.low_day));
  renderWeeks(n); renderEvents(n); renderInsights(n);
}

function renderWeeks(n){
  const weeks=Math.ceil(n/7), rows=[];
  for(let k=0;k<weeks;k++){const a=k*7,b=Math.min(n,a+7);rows.push({label:`${fmtDate(dayDate(a))} – ${fmtDate(dayDate(b))}`,net:data.balances[b]-data.balances[a],end:data.balances[b]})}
  const max=Math.max(...rows.map(r=>Math.abs(r.net)),1);
  $('#weekRange').textContent='Net change per week';
  $('#weekBars').innerHTML=rows.map(r=>`<div class="wk"><span class="wk-l">${esc(r.label)}</span><div class="wk-track"><i class="${r.net>=0?'pos':'neg'}" style="width:${Math.max(4,Math.abs(r.net)/max*100)}%"></i></div><b class="${r.net>=0?'pos':'neg'}">${signed(r.net)}</b><small>${money(r.end)}</small></div>`).join('');
}

function renderEvents(n){
  const evs=data.events.filter(e=>e[0]<=n);
  $('#eventRange').textContent=`Next ${n} days`;
  $('#eventList').innerHTML=evs.length?evs.map(e=>{
    const bal=data.balances[e[0]], under=bal<buf();
    return `<div class="event-item"><span class="date"><b>${fmtDate(dayDate(e[0]),{day:'numeric'})}</b>${fmtDate(dayDate(e[0]),{month:'short'})}</span><div style="flex:1"><b>${esc(e[2])}</b><small>${e[3]==='in'?'Expected money in':'Expected money out'} · balance after ${money(bal)}${under?' · <span class="neg">below buffer</span>':''}</small></div><span class="amount ${e[3]}">${e[3]==='in'?'+':'−'}${money(Math.abs(e[1]))}</span></div>`}).join('')
    :'<div class="empty">No repeating payments found in this window. The chart follows your typical day-to-day movement.</div>';
}

function renderInsights(n){
  const wi=data.windows[n], c=data.cash, B=buf(), out=[];
  const bigOut=data.events.filter(e=>e[0]<=n&&e[1]<0).sort((a,b)=>a[1]-b[1])[0];
  const bigIn=data.events.filter(e=>e[0]<=n&&e[1]>0).sort((a,b)=>b[1]-a[1])[0];
  if(wi.low<B) out.push(['warn',`Cash dips ${money(B-wi.low)} under your buffer`,`Lowest on ${fmtDate(dayDate(wi.low_day))}. Consider chasing invoices or timing payments before then.`]);
  else out.push(['ok','No cash gap in this window',`Your lowest balance is ${money(wi.low)}, ${money(wi.low-B)} above the buffer.`]);
  if(bigOut) out.push(['info',`Biggest payment: ${bigOut[2]}`,`${money(Math.abs(bigOut[1]))} around ${fmtDate(dayDate(bigOut[0]))}.`]);
  if(bigIn) out.push(['info',`Biggest expected income: ${bigIn[2]}`,`${money(bigIn[1])} around ${fmtDate(dayDate(bigIn[0]))}.`]);
  if(c.runway_days!=null) out.push(['info',`About ${c.runway_days} days of cover`,`At recent spending of ${money(c.avg_daily_out)} a day against ${money(c.avg_daily_in)} coming in.`]);
  $('#insightList').innerHTML=out.map(([t,h,p])=>`<div class="insight ${t}"><i></i><div><b>${esc(h)}</b><small>${esc(p)}</small></div></div>`).join('');
}

function renderActivity(){
  const evs=data.events.slice(0,3);
  $('#homeActivity').innerHTML=evs.map(e=>`<div class="activity-item"><span class="activity-icon">${e[3]==='in'?'↗':'↘'}</span><div><b>${esc(e[2])}</b><small>${fmtDate(dayDate(e[0]),{weekday:'short',day:'numeric',month:'short'})} · ${e[3]==='in'?'Expected money in':'Expected money out'}</small></div><span class="amount ${e[3]}">${e[3]==='in'?'+':'−'}${money(Math.abs(e[1]))}</span></div>`).join('')
    ||'<div class="white-card"><small class="muted">No upcoming payments found yet.</small></div>';
}

/* Available cash sheet */
function renderCash(){
  const c=data.cash, B=buf(), h=c.history||[];
  $('#csValue').textContent=money(data.start);
  $('#csAsOf').textContent=(data.demo?'Sample data · ':'')+'As of '+fmtDate(anchor(),{weekday:'long',day:'numeric',month:'long'});
  const d30=h.length>1?data.start-h[0]:null, cd=$('#csDelta');
  if(d30==null){cd.textContent='';}else{cd.textContent=`${signed(d30)} in ${h.length-1} days`;cd.className='cs-delta '+(d30>=0?'pos':'neg')}
  sparkline(h);
  const net=c.avg_daily_in-c.avg_daily_out;
  $('#csStats').innerHTML=[
    ['Safe to spend',money(c.safe_to_spend),'Cash above your buffer'],
    ['Cash buffer',money(B),'Your safety cushion'],
    ['Cash cover',c.runway_days==null?'Growing':c.runway_days+' days','At recent spending'],
    ['Average day',signed(net),'Money in minus out']
  ].map(([a,b,s])=>`<div class="cs-stat"><span>${a}</span><b>${esc(b)}</b><small>${s}</small></div>`).join('');
  const inn=c.avg_daily_in*30,out=c.avg_daily_out*30,mx=Math.max(inn,out,1);
  $('#csFlow').innerHTML=`<div class="fl"><span>Money in</span><div><i class="pos" style="width:${inn/mx*100}%"></i></div><b class="pos">${money(inn)}</b></div><div class="fl"><span>Money out</span><div><i class="neg" style="width:${out/mx*100}%"></i></div><b class="neg">${money(out)}</b></div>`;
  const cats=c.categories||[], cm=Math.max(...cats.map(x=>x.amount),1);
  $('#csCats').innerHTML=cats.length?cats.map(x=>`<div class="cat"><span>${esc(x.name)}</span><div><i style="width:${x.amount/cm*100}%"></i></div><b>${money(x.amount)}</b></div>`).join(''):'<div class="empty">Upload a statement to see spending by category.</div>';
  const rc=c.recent||[];
  $('#csRecent').innerHTML=rc.length?rc.map(t=>`<div class="event-item"><span class="date"><b>${new Date(t.date.slice(0,10)+'T00:00:00').getDate()}</b>${fmtDate(new Date(t.date.slice(0,10)+'T00:00:00'),{month:'short'})}</span><div style="flex:1"><b>${esc(t.desc)}</b><small>${t.amount>=0?'Money in':'Money out'}</small></div><span class="amount ${t.amount>=0?'in':'out'}">${signed(t.amount)}</span></div>`).join(''):'<div class="empty">No transactions yet.</div>';
}

function renderDocs(filter='all'){
  let docs=(data.documents||[]).map(d=>({...d,type:d.title.toLowerCase().includes('statement')?'statement':d.title.toLowerCase().includes('invoice')?'invoice':'receipt',icon:esc(d.title.split('.').pop().toUpperCase().slice(0,4))}));
  if(filter!=='all')docs=docs.filter(d=>d.type===filter);
  $('#documentList').innerHTML=docs.map(d=>`<div class="doc-item"><span class="doc-icon ${d.type}">${d.icon}</span><div class="doc-meta"><b>${esc(d.title)}</b><small>${esc(d.text)}</small></div><span>›</span></div>`).join('')||'<div class="white-card"><small class="muted">No documents in this filter yet.</small></div>';
}
function renderSignals(){const s=(data.signals||[]).filter(x=>x.type==='tax');$('#signalList').innerHTML=s.map(x=>`<div class="signal-item"><span class="signal-mark">✓</span><div class="signal-copy"><b>${esc(x.title)}</b><small>${esc(x.text)}</small></div><span class="signal-amount">${esc(x.amount||'Review')}</span></div>`).join('')||'<div class="white-card"><small class="muted">No tax signals found yet. Upload a statement with descriptions to find some.</small></div>'}

/* ---------- Navigation + sheets ---------- */
function go(screen){
  $$('.screen').forEach(s=>s.classList.toggle('active',s.dataset.screen===screen));
  $$('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.nav===screen));
  document.body.classList.toggle('screen-wide',screen==='cashflow');
  window.scrollTo({top:0,behavior:'smooth'});
  if(screen==='cashflow'&&data) requestAnimationFrame(()=>drawLarge(days));
}
function openSheet(id){$('#sheetBackdrop').classList.add('show');$('#'+id).classList.add('open');$('#'+id).setAttribute('aria-hidden','false');$('#fab').classList.add('open');if(id==='cashSheet')requestAnimationFrame(()=>sparkline((data.cash||{}).history||[]))}
function closeSheet(id){$('#'+id).classList.remove('open');$('#'+id).setAttribute('aria-hidden','true');if(!$$('.sheet.open').length){$('#sheetBackdrop').classList.remove('show');$('#fab').classList.remove('open')}}
async function load(){try{const r=await fetch('/api/dashboard',{cache:'no-store'});if(r.ok)data=await r.json()}catch(e){}render()}

const hr=new Date().getHours();$('#greeting').textContent=(hr<12?'Good morning':hr<18?'Good afternoon':'Good evening');$('#todayLabel').textContent=new Date().toLocaleDateString('en-MY',{weekday:'long',day:'numeric',month:'short'}).toUpperCase();
$$('[data-nav]').forEach(b=>b.onclick=()=>go(b.dataset.nav));
$$('[data-action]').forEach(b=>b.onclick=()=>{const a=b.dataset.action;if(a==='upload')openSheet('uploadSheet');else go(a==='forecast'?'cashflow':a)});
$('#fab').onclick=()=>openSheet('uploadSheet');$('#attentionBtn').onclick=()=>go('cashflow');$('#bellBtn').onclick=()=>openSheet('notifySheet');
const cc=$('#cashCard');cc.onclick=()=>openSheet('cashSheet');cc.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openSheet('cashSheet')}};
$('#refreshBtn').onclick=async e=>{e.stopPropagation();await load();toast('Cash forecast refreshed')};
$('#csForecast').onclick=()=>{closeSheet('cashSheet');go('cashflow')};$('#csUpload').onclick=()=>{closeSheet('cashSheet');openSheet('uploadSheet')};
$('#profileBtn').onclick=()=>go('more');$('#seeAllBtn').onclick=()=>go('more');
$$('[data-close]').forEach(b=>b.onclick=()=>closeSheet(b.dataset.close));$('#sheetBackdrop').onclick=()=>$$('.sheet.open').forEach(s=>closeSheet(s.id));
document.addEventListener('keydown',e=>{if(e.key==='Escape')$$('.sheet.open').forEach(s=>closeSheet(s.id))});
$$('.segmented button').forEach(b=>b.onclick=()=>{$$('.segmented button').forEach(x=>x.classList.remove('active'));b.classList.add('active');days=+b.dataset.days;drawLarge(days)});
$$('.filter').forEach(b=>b.onclick=()=>{$$('.filter').forEach(x=>x.classList.remove('active'));b.classList.add('active');renderDocs(b.dataset.filter)});
let rz;window.addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(()=>{if(data){drawLarge(days);sparkline((data.cash||{}).history||[])}},120)});

/* ---------- Upload ---------- */
function setUploadMsg(text,kind){const m=$('#uploadMessage');m.textContent=text;m.className='upload-message'+(kind?' '+kind:'')}
$('#fileInput').onchange=e=>{selectedFile=e.target.files[0]||null;$('#selectedFile').textContent=selectedFile?selectedFile.name:'No file selected';$('#fileLabel').textContent=selectedFile?selectedFile.name:'Choose a file';setUploadMsg('')};
$('#uploadSubmit').onclick=async()=>{
  if(!selectedFile){setUploadMsg('Choose a file first.','error');return}
  const btn=$('#uploadSubmit');btn.disabled=true;setUploadMsg('Analysing…','');
  try{
    // Read the file into memory first so the upload still works if the file changes on disk
    // (some browsers abort with "Failed to fetch" otherwise).
    const blob=new Blob([await selectedFile.arrayBuffer()],{type:selectedFile.type||'application/octet-stream'});
    const fd=new FormData();fd.append('file',blob,selectedFile.name);
    let r;
    try{r=await fetch('/api/upload',{method:'POST',body:fd})}
    catch(_){throw new Error('Cannot reach the Finvia server. Check your connection and that the server is running, then try again.')}
    let j=null;try{j=await r.json()}catch(_){}
    if(!r.ok)throw new Error((j&&j.detail)||`The server returned an error (${r.status}). Please try again.`);
    if(j.ok===false){setUploadMsg(j.message||'Could not analyse this file.','error');return}
    data=j.dashboard;render();setUploadMsg(j.message||'Analysis complete.','ok');toast('Document analysed');
    go('cashflow');setTimeout(()=>closeSheet('uploadSheet'),900);
  }catch(e){setUploadMsg(e.message,'error')}
  finally{btn.disabled=false}
};

$('#reportBtn').onclick=async()=>{openSheet('reportSheet');$('#reportBody').innerHTML='<p class="muted">Loading report…</p>';try{const r=await fetch('/api/tax-report');const j=await r.json();$('#reportBody').innerHTML=(j.items||[]).map(x=>`<div class="report-row"><b>${esc(x.title)}</b><small>${esc(x.text||x.description||'Review supporting documents and eligibility.')}</small></div>`).join('')||'<div class="report-row"><b>No report items yet</b><small>Upload invoices or receipts to create signals.</small></div>'}catch(e){$('#reportBody').innerHTML='<div class="report-row"><b>Report unavailable</b><small>Please try again.</small></div>'}};
$('#referralBtn').onclick=async()=>{if(!$('#consent').checked){toast('Please give consent before requesting a referral');return}$('#referralBtn').disabled=true;try{const r=await fetch('/api/referral',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({consent:true})});const j=await r.json();if(!r.ok)throw new Error(j.detail||'Request failed');toast('Referral request submitted');$('#referralBtn').textContent='Referral submitted'}catch(e){toast(e.message)}finally{$('#referralBtn').disabled=false}};
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();deferredInstall=e});$('#installBtn').onclick=async()=>{if(deferredInstall){deferredInstall.prompt();await deferredInstall.userChoice;deferredInstall=null}else toast('Use your browser menu to add Finvia to your home screen')};$('#aboutBtn').onclick=()=>toast('Finvia prototype · SME cash, tax signals and financing referral');
if('serviceWorker' in navigator)navigator.serviceWorker.register('/service-worker.js').catch(()=>{});load();
