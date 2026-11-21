const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pad=n=>String(n).padStart(2,'0');
const fmt=d=>new Date(d+'T00:00:00Z').toLocaleDateString('nl-NL',{weekday:'long',day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});
const STATUS={feit:'Feit',reconstructie:'Reconstructie',onzeker:'Onzeker'};

function histDate(){
  const n=new Date();let y=n.getFullYear()-87,m=n.getMonth()+1,d=n.getDate();
  const leap=y%4===0&&(y%100!==0||y%400===0);
  if(m===2&&d===29&&!leap)d=28;
  return `${y}-${pad(m)}-${pad(d)}`;
}
function article(a){
  const src=(a.sources||[]).filter(s=>String(s.url).startsWith('https://'))
    .map(s=>`<a href="${esc(s.url)}" rel="noopener" target="_blank">${esc(s.title)}</a>`).join('; ');
  return `<article><p class="sec">${esc(a.section)}</p><h3>${esc(a.headline)}</h3>
  <p><span class="loc">${esc(a.location)}</span>. ${a.body.map(esc).join('</p><p>')}</p>
  <p class="ctx">${esc(a.context)}</p>
  <p class="meta"><span class="tag">${esc(STATUS[a.status]||'Onzeker')}</span>Bronnen: ${src||'geen'}</p></article>`;
}
function renderEdition(e,notice){
  $('#edNo').textContent=`Editie nr. ${e.number}`;
  $('#edDate').textContent=fmt(e.date);
  const n=$('#notice');n.hidden=!notice;n.textContent=notice||'';
  const [lead,...rest]=e.articles;
  $('#lead').innerHTML=lead?`<div class="lead"><p class="sec">${esc(lead.section)}</p><h2>${esc(lead.headline)}</h2>
   <p class="meta"><span class="loc">${esc(lead.location)}</span></p>
   <div class="body"><p>${lead.body.map(esc).join('</p><p>')}</p><p class="ctx">${esc(lead.context)}</p></div>
   <p class="meta"><span class="tag">${esc(STATUS[lead.status]||'Onzeker')}</span>Bronnen: ${(lead.sources||[]).filter(s=>String(s.url).startsWith('https://')).map(s=>`<a href="${esc(s.url)}" rel="noopener" target="_blank">${esc(s.title)}</a>`).join('; ')}</p></div>`:'';
  $('#more').innerHTML=rest.map(article).join('');
}
function renderArchive(items){
  const q=$('#q').value.trim().toLowerCase();
  const hit=items.filter(i=>!q||(i.date+' '+i.headline+' '+(i.topics||[]).join(' ')).toLowerCase().includes(q));
  $('#list').innerHTML=hit.map(i=>`<li><a href="#d=${esc(i.date)}">${esc(fmt(i.date))}</a> – editie ${i.number}<br>${esc(i.headline)}</li>`).join('')||'<li>Geen edities gevonden.</li>';
}
async function route(idx){
  const h=location.hash;const arch=h==='#archief';
  $('#front').hidden=arch;$('#archief').hidden=!arch;
  $('#navArch').classList.toggle('on',arch);$('#navFront').classList.toggle('on',!arch);
  if(arch){renderArchive(idx);return;}
  const want=(h.match(/^#d=(\d{4}-\d{2}-\d{2})$/)||[])[1]||histDate();
  const hit=idx.find(i=>i.date===want)||idx[0];
  const notice=hit.date!==want?`Voor ${fmt(want)} is nog geen editie beschikbaar. Hier staat de laatste editie.`:'';
  try{
    const r=await fetch(`data/editions/${hit.date}.json`);
    if(!r.ok)throw new Error(r.status);
    renderEdition(await r.json(),notice);
  }catch(err){$('#lead').innerHTML='<p>De editie kon niet worden geladen. Probeer het later opnieuw.</p>';}
}
(async()=>{
  try{
    const idx=(await (await fetch('data/index.json')).json()).editions.sort((a,b)=>b.date.localeCompare(a.date));
    $('#q').addEventListener('input',()=>renderArchive(idx));
    $('#jump').addEventListener('change',e=>{if(e.target.value)location.hash='#d='+e.target.value;});
    addEventListener('hashchange',()=>route(idx));
    route(idx);
  }catch(err){$('#lead').innerHTML='<p>Het archief kon niet worden geladen.</p>';}
})();
