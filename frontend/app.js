const state={user:null,csrf:"",view:"overview",rfqs:[],rates:[],selectedRfq:null,quote:null,history:[]};
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v==null?"":v).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;");
const money=(v,d=(v!=null&&Math.abs(v)>=10000?0:2))=>v==null?"—":new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR",minimumFractionDigits:d,maximumFractionDigits:d}).format(v);
const nfmt=(v,d=2)=>Number(v||0).toLocaleString("en-IN",{maximumFractionDigits:d});
const dfmt=v=>v?new Date(v+"T00:00:00").toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"numeric"}):"—";
const statusName=s=>({pending_approval:"Pending approval",returned:"Returned"}[s]||(s||"").replaceAll("_"," "));
const status=s=>'<span class="status-pill status-'+esc(s)+'">'+esc(statusName(s))+"</span>";

async function api(path,opt={}){
  const headers=new Headers(opt.headers||{});
  if(opt.body&&!(opt.body instanceof FormData))headers.set("Content-Type","application/json");
  if(opt.method&&opt.method!=="GET"&&state.csrf)headers.set("X-CSRF-Token",state.csrf);
  const res=await fetch("/api"+path,{credentials:"same-origin",...opt,headers});
  const data=(res.headers.get("content-type")||"").includes("application/json")?await res.json():await res.blob();
  if(res.status===401){state.user=null;state.csrf="";showLogin()}
  if(!res.ok)throw new Error(data.detail||"Request failed ("+res.status+")");
  return data;
}
function toast(text,type=""){const x=document.createElement("div");x.className="toast "+type;x.textContent=text;$("#toast-region").append(x);setTimeout(()=>x.remove(),3600)}
function showLogin(){$("#app-shell").classList.add("hidden");$("#login-view").classList.remove("hidden")}
function showApp(){
  $("#login-view").classList.add("hidden");$("#app-shell").classList.remove("hidden");
  const initials=state.user.display_name.split(/[ ·]/).filter(Boolean).map(x=>x[0]).slice(0,2).join("").toUpperCase();
  $("#user-name").textContent=state.user.display_name;$("#user-role").textContent=state.user.role==="sales"?"Sales Head":"Estimator";
  $("#user-avatar").textContent=initials;$("#topbar-initials").textContent=initials;
  $$(".sales-only").forEach(x=>x.classList.toggle("hidden",state.user.role!=="sales"));
  $$(".estimator-only").forEach(x=>x.classList.toggle("hidden",state.user.role!=="estimator"));if(!state.rates.length)api("/rates").then(x=>{state.rates=x.items}).catch(()=>{});loadView("overview");
}
async function boot(){try{const x=await api("/me");state.user=x.user;state.csrf=x.csrf_token;showApp()}catch{showLogin()}}
$("#login-form").addEventListener("submit",async e=>{e.preventDefault();$("#login-notice")?.classList.add("hidden");const b=$("#login-form button[type=submit]");b.disabled=true;try{const x=await api("/auth/login",{method:"POST",body:JSON.stringify({username:$("#login-username").value,password:$("#login-password").value})});state.user=x.user;state.csrf=x.csrf_token;showApp()}catch(err){toast(err.message,"error")}finally{b.disabled=false}});
$("#toggle-password").addEventListener("click",()=>{const i=$("#login-password");i.type=i.type==="password"?"text":"password";$("#toggle-password").textContent=i.type==="password"?"Show":"Hide"});
$$("[data-user]").forEach(b=>b.addEventListener("click",()=>{$("#login-username").value=b.dataset.user;$("#login-password").value=b.dataset.pass;$("#login-form").requestSubmit()}));
async function confirmSignOut(){
  try{await api("/auth/logout",{method:"POST"})}catch{}
  state.user=null;state.csrf="";state.selectedRfq=null;state.quote=null;
  $("#login-notice").textContent="You’re signed out. Sign in again to return to your workspace.";
  $("#login-notice").classList.remove("hidden");
  $("#login-password").value="";
  closeModal();
  showLogin();
}

async function switchUserQuick(username,password){
  try{
    const x=await api("/auth/login",{method:"POST",body:JSON.stringify({username,password})});
    state.user=x.user;
    state.csrf=x.csrf_token;
    closeModal();
    showApp();
    toast("Switched active profile to "+x.user.display_name+" ("+(x.user.role==="sales"?"Sales Head":"Estimator")+").","success");
  }catch(err){
    toast(err.message,"error");
  }
}

function openUserProfileModal(){
  if(!state.user)return;
  const isSales=state.user.role==="sales";
  const initials=state.user.display_name.split(/[ 	]/).filter(Boolean).map(x=>x[0]).slice(0,2).join("").toUpperCase();
  const roleName=isSales?"Sales Head":"Estimator";
  const roleClass=isSales?"badge-amber":"status-approved";
  const userEmail=state.user.email||(isSales?"sales@demo.local":"estimator@demo.local");

  const body='<div style="display:flex;flex-direction:column;gap:14px">'+
    '<div style="display:flex;align-items:center;gap:12px;padding:12px 14px;background:#f7f9f7;border:1px solid #edf0ed;border-radius:10px">'+
      '<div class="avatar '+(isSales?"avatar-amber":"avatar-green")+'" style="width:42px;height:42px;font-size:14px;font-weight:700">'+esc(initials)+'</div>'+
      '<div style="flex:1">'+
        '<div style="display:flex;align-items:center;gap:8px">'+
          '<strong style="font-size:13.5px;color:#1e3128">'+esc(state.user.display_name)+'</strong>'+
          '<span class="status-pill '+roleClass+'">'+esc(roleName)+'</span>'+
        '</div>'+
        '<small style="color:#6d7f76;font-size:11px;display:block;margin-top:2px">'+esc(userEmail)+'</small>'+
      '</div>'+
    '</div>'+
    '<div>'+
      '<div class="eyebrow" style="margin-bottom:7px">WORKSPACE SESSION</div>'+
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:7px;font-size:11px">'+
        '<div style="padding:9px 11px;background:#fff;border:1px solid #e7ebe8;border-radius:7px">'+
          '<span style="color:#809188;font-size:9.5px;display:block">Facility</span>'+
          '<strong style="color:#2a3d34">Company A · Pune / Chakan</strong>'+
        '</div>'+
        '<div style="padding:9px 11px;background:#fff;border:1px solid #e7ebe8;border-radius:7px">'+
          '<span style="color:#809188;font-size:9.5px;display:block">Cost Engine</span>'+
          '<strong style="color:#2a3d34">Deterministic (Decimal)</strong>'+
        '</div>'+
        '<div style="padding:9px 11px;background:#fff;border:1px solid #e7ebe8;border-radius:7px">'+
          '<span style="color:#809188;font-size:9.5px;display:block">AI Gateway</span>'+
          '<strong style="color:#24634d">AgentRouter · gpt-6.1-sol</strong>'+
        '</div>'+
        '<div style="padding:9px 11px;background:#fff;border:1px solid #e7ebe8;border-radius:7px">'+
          '<span style="color:#809188;font-size:9.5px;display:block">Role Scope</span>'+
          '<strong style="color:#2a3d34">'+(isSales?"Review & Approvals":"Cost Estimation & Ingestion")+'</strong>'+
        '</div>'+
      '</div>'+
    '</div>'+
    '<div>'+
      '<div class="eyebrow" style="margin-bottom:7px">SWITCH DEMO ROLE</div>'+
      '<div style="display:grid;gap:6px">'+
        '<button type="button" class="button button-outline" style="justify-content:flex-start;text-align:left;padding:8px 12px;height:auto;display:flex;align-items:center" id="switch-user-ae">'+
          '<span class="avatar avatar-green" style="width:24px;height:24px;font-size:9px;margin-right:10px">AE</span>'+
          '<div style="flex:1"><strong style="font-size:11px">Anand (Estimator)</strong><small style="display:block;color:#788681;font-size:9.5px">estimator@demo.local · Drafting & Costing</small></div>'+
          (!isSales?'<span style="color:#24634d;font-size:10.5px;font-weight:700">Active ✓</span>':'<span style="color:#6d7f76;font-size:10.5px">Switch →</span>')+
        '</button>'+
        '<button type="button" class="button button-outline" style="justify-content:flex-start;text-align:left;padding:8px 12px;height:auto;display:flex;align-items:center" id="switch-user-ms">'+
          '<span class="avatar avatar-amber" style="width:24px;height:24px;font-size:9px;margin-right:10px">MS</span>'+
          '<div style="flex:1"><strong style="font-size:11px">Meera (Sales Head)</strong><small style="display:block;color:#788681;font-size:9.5px">sales@demo.local · Approvals view enabled</small></div>'+
          (isSales?'<span style="color:#24634d;font-size:10.5px;font-weight:700">Active ✓</span>':'<span style="color:#6d7f76;font-size:10.5px">Switch →</span>')+
        '</button>'+
      '</div>'+
    '</div>'+
  '</div>';

  const footer='<button class="button button-danger" id="profile-signout-btn">Sign out</button><button class="button" data-close>Close</button>';
  showModal("Active Account", "User profile and workspace session", body, footer);

  $("#switch-user-ae")?.addEventListener("click",()=>switchUserQuick("estimator@demo.local","estimate-demo"));
  $("#switch-user-ms")?.addEventListener("click",()=>switchUserQuick("sales@demo.local","approve-demo"));
  $("#profile-signout-btn")?.addEventListener("click",()=>{closeModal();confirmSignOut()});
}

function openHelpModal(){
  const body='<div style="display:flex;flex-direction:column;gap:13px;line-height:1.5;font-size:11px;color:#2c3f36">'+
    '<div class="note-box" style="background:#eaf3ee;border:1px solid #d3e5da;color:#1e4b3b;padding:11px 13px">'+
      '<strong>ForgeQuote Estimation Workspace</strong> delivers deterministic, audit-proof costing for closed-die forging. All pricing is computed through Python Decimal math; the AI assistant is strictly informational.'+
    '</div>'+
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:9px">'+
      '<div style="padding:11px;background:#f7f9f7;border:1px solid #e7ebe8;border-radius:8px">'+
        '<div style="font-weight:700;color:#1e352b;margin-bottom:3px;font-size:11.5px">1. RFQ Register & Ingestion</div>'+
        '<div style="color:#576b61;font-size:10px">Ingest RFQ packages or select sample parts. Review customer specifications, material alloys (EN19, 20MnCr5), and batch quantities.</div>'+
      '</div>'+
      '<div style="padding:11px;background:#f7f9f7;border:1px solid #e7ebe8;border-radius:8px">'+
        '<div style="font-weight:700;color:#1e352b;margin-bottom:3px;font-size:11.5px">2. Deterministic Costing</div>'+
        '<div style="color:#576b61;font-size:10px">Configure gross/net weights, flash scrap credit, machine tonnage rates, cycle times, and tooling amortization. Select volumes and click <b>Calculate Quote</b>.</div>'+
      '</div>'+
      '<div style="padding:11px;background:#f7f9f7;border:1px solid #e7ebe8;border-radius:8px">'+
        '<div style="font-weight:700;color:#1e352b;margin-bottom:3px;font-size:11.5px">3. Sales Governance & Approvals</div>'+
        '<div style="color:#576b61;font-size:10px">Estimators submit revisions for review. Sales Head reviews margins, line-item breakdowns, and approves or returns with mandatory recorded feedback.</div>'+
      '</div>'+
      '<div style="padding:11px;background:#f7f9f7;border:1px solid #e7ebe8;border-radius:8px">'+
        '<div style="font-weight:700;color:#1e352b;margin-bottom:3px;font-size:11.5px">4. AI Quote Assistant</div>'+
        '<div style="color:#576b61;font-size:10px">Powered by <b>gpt-6.1-sol</b> via AgentRouter. Searches historical parts, routing keys, and material specs formatted in clean tables. AI never calculates prices.</div>'+
      '</div>'+
    '</div>'+
    '<div style="padding:10px 12px;background:#ffffff;border:1px solid #e2e8e4;border-radius:8px">'+
      '<div class="eyebrow" style="margin-bottom:5px">KEYBOARD SHORTCUTS</div>'+
      '<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:10.5px;color:#495d53">'+
        '<div><kbd style="background:#eef1ef;border:1px solid #d2ded7;padding:2px 5px;border-radius:4px;font-family:monospace;font-size:9.5px">Ctrl</kbd> + <kbd style="background:#eef1ef;border:1px solid #d2ded7;padding:2px 5px;border-radius:4px;font-family:monospace;font-size:9.5px">K</kbd> : Global search</div>'+
        '<div><kbd style="background:#eef1ef;border:1px solid #d2ded7;padding:2px 5px;border-radius:4px;font-family:monospace;font-size:9.5px">?</kbd> : Open this guide</div>'+
        '<div><kbd style="background:#eef1ef;border:1px solid #d2ded7;padding:2px 5px;border-radius:4px;font-family:monospace;font-size:9.5px">Esc</kbd> : Close open modal</div>'+
      '</div>'+
    '</div>'+
    '<div style="display:flex;align-items:center;gap:6px;font-size:9.5px;color:#7c8d85">'+
      '<span class="status-led small-led"></span>'+
      '<span>All rows marked <b style="color:#7b5420">SYNTHETIC DEMO</b> are generated sample records clearly isolated from customer data.</span>'+
    '</div>'+
  '</div>';

  const footer='<button class="button button-primary" data-close>Got it</button>';
  showModal("ForgeQuote Guide & Shortcuts","Estimation workflow, governance, and quick reference",body,footer,true);
}

function triggerGlobalSearch(){
  const input=$("#global-search");
  if(!input)return;
  const q=(input.value||"").trim();
  state.historyQuery=q;
  loadView("history");
  if(q){
    toast('Filtering quote history for "'+q+'"...',"info");
  }
}

$("#search-global-box")?.addEventListener("click",e=>{
  const input=$("#global-search");
  if(input&&e.target!==input){
    input.focus();
    input.select();
  }
});

$("#global-search")?.addEventListener("keydown",e=>{
  if(e.key==="Enter"){
    triggerGlobalSearch();
  }else if(e.key==="Escape"){
    e.target.blur();
  }
});

$("#help-button")?.addEventListener("click",openHelpModal);
$("#topbar-initials")?.addEventListener("click",openUserProfileModal);
$("#user-menu")?.addEventListener("click",openUserProfileModal);

window.addEventListener("keydown",e=>{
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="k"){
    e.preventDefault();
    const input=$("#global-search");
    if(input){input.focus();input.select()}
  }else if(e.key==="?"&&!["INPUT","TEXTAREA"].includes(document.activeElement?.tagName)){
    e.preventDefault();
    openHelpModal();
  }else if(e.key==="Escape"&&$("#modal-root")?.children.length){
    closeModal();
  }
});
$(".main-nav").addEventListener("click",e=>{const x=e.target.closest("[data-view]");if(x&&!x.classList.contains("hidden"))loadView(x.dataset.view)});

function showModal(title,subtitle,body,footer="",wide=false){
  $("#modal-root").innerHTML='<div class="modal-backdrop" data-backdrop><section class="modal '+(wide?"modal-wide":"")+'" role="dialog" aria-modal="true"><header class="modal-head"><div><h2>'+esc(title)+'</h2><p>'+esc(subtitle)+'</p></div><button class="close-button" data-close aria-label="Close">×</button></header><div class="modal-body">'+body+'</div>'+(footer?'<footer class="modal-foot">'+footer+"</footer>":"")+"</section></div>";
  $("#modal-root [data-close]").addEventListener("click",closeModal);$("#modal-root [data-backdrop]").addEventListener("click",e=>{if(e.target.matches("[data-backdrop]"))closeModal()});
}
function closeModal(){$("#modal-root").innerHTML=""}
function confirmModal({title="Confirmation",subtitle="Please confirm your action",message="Are you sure?",confirmText="Confirm",confirmClass="button-primary",onConfirm}){
  const body='<div class="note-box" style="font-size:11.5px;padding:14px;color:#2c3e35;line-height:1.6">'+message+'</div>';
  const footer='<button class="button" data-close>Cancel</button><button class="button '+confirmClass+'" id="modal-confirm-btn">'+esc(confirmText)+'</button>';
  showModal(title,subtitle,body,footer);
  $("#modal-root [data-close]").onclick=closeModal;
  $("#modal-confirm-btn").onclick=async()=>{
    closeModal();
    if(onConfirm)await onConfirm();
  };
}
function heading(kicker,title,desc,actions=""){return '<div class="page-heading"><div><div class="eyebrow">'+esc(kicker)+'</div><h1>'+esc(title)+'</h1><p>'+esc(desc)+'</p></div><div class="heading-actions">'+actions+"</div></div>"}
function banner(text="Fictional examples keep this preview populated. They are not Company A quote history."){return '<div class="demo-banner"><span>✳</span><span><strong>DEMO DATA</strong> · '+esc(text)+'</span><span class="banner-right">Resettable sample workspace</span></div>'}
function loading(title){$("#view-root").innerHTML=heading("WORKSPACE",title,"Loading workspace…")+'<section class="panel"><div class="form-section"><div class="loading-line" style="width:55%"></div><div class="loading-line" style="width:82%;margin-top:15px"></div></div></section>'}
async function loadView(view){
  state.view=view;$$(".nav-item").forEach(x=>x.classList.toggle("active",x.dataset.view===view));
  const names={overview:"RFQ register",costing:"Costing workspace",rates:"Rate master",approvals:"Approvals",history:"Quote history"};
  $("#breadcrumb-current").textContent=names[view]||"Workspace";loading(names[view]||"Workspace");
  try{if(view==="overview")await renderOverview();else if(view==="costing")await renderCosting();else if(view==="rates")await renderRates();else if(view==="approvals")await renderApprovals();else await renderHistory()}catch(e){$("#view-root").innerHTML=heading("WORKSPACE","Couldn’t load this view",e.message,'<button class="button" id="retry">Try again</button>');$("#retry").onclick=()=>loadView(view)}
}
function row(r){const over=["estimating","pending_approval"].includes(r.status)&&new Date(r.due_date+"T00:00:00")<new Date(new Date().toDateString());const owner=state.user.role==="sales"?'<button class="owner-assign" data-owner-rfq="'+r.id+'">'+esc(r.owner)+'<small>Reassign</small></button>':esc(r.owner);return '<tr class="row-open" data-rfq="'+r.id+'"><td class="rfq-cell"><strong>'+esc(r.rfq_number)+'</strong><small>'+esc(r.source_label)+'</small></td><td class="customer-cell">'+esc(r.customer)+(r.synthetic?' <span class="demo-badge">DEMO</span>':"")+'</td><td>'+dfmt(r.due_date)+(over?' <span class="date-cell overdue">· overdue</span>':"")+'</td><td>'+owner+'</td><td><span class="part-count">'+r.part_count+'</span></td><td>'+status(r.status)+'</td><td class="amount">'+money(r.annual_value)+'</td><td><button class="icon-action" aria-label="Open RFQ details">···</button></td></tr>'}
async function renderOverview(){
  const d=await api("/rfqs");state.rfqs=d.items;$("#rfq-nav-count").textContent=d.total;
  const c={};["estimating","pending_approval","approved","sent","won","lost"].forEach(k=>c[k]=d.items.filter(r=>r.status===k).length);if(state.user.role==="sales")$("#approval-nav-count").textContent=c.pending_approval||"0";
  const stats=[["In estimation",c.estimating,"Active estimator work","◫"],["Awaiting approval",c.pending_approval,"Sales Head review queue","✓"],["Quotes sent",c.sent,"Awaiting customer outcome","↗"],["Won in demo",c.won,"Synthetic outcomes included","⌁"]];
  const act=(state.user.role==="estimator"?'<button class="button button-primary" id="new-rfq">＋ New RFQ</button>':"");
  $("#view-root").innerHTML=heading("RFQ PIPELINE","Good "+(new Date().getHours()<12?"morning":"afternoon")+", "+state.user.display_name.split(" ·")[0],"Your RFQ pipeline, at a glance.",'<button class="button" id="to-history">↥ Import history</button>'+act)+banner()+'<section class="metric-grid">'+stats.map((x,i)=>'<article class="metric-card"><div class="metric-label">'+x[0]+'<span class="metric-accent '+(i===1?"amber":i===2?"blue":"")+'">'+x[3]+'</span></div><div class="metric-value">'+x[1]+'</div><div class="metric-foot">'+x[2]+'</div></article>').join("")+'</section><section class="panel"><div class="panel-head"><div><div class="panel-title">RFQ register</div><span class="panel-subtitle">'+d.total+' RFQs · due dates shown locally</span></div><div class="panel-actions"><select class="filter-select" id="status-filter"><option value="">All statuses</option><option value="estimating">Estimating</option><option value="pending_approval">Pending approval</option><option value="approved">Approved</option><option value="sent">Sent</option><option value="won">Won</option><option value="lost">Lost</option></select><input class="filter-input" id="rfq-filter" placeholder="Search RFQ or customer"/></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>RFQ / source</th><th>Customer</th><th>Due date</th><th>Owner</th><th>Parts</th><th>Status</th><th>Annual value</th><th></th></tr></thead><tbody id="rfq-body">'+(d.items.map(row).join("")||'<tr><td class="table-empty" colspan="8"><strong>No RFQs yet</strong>Create one to start a quote.</td></tr>')+'</tbody></table></div><div class="table-footer"><span>Showing <b>'+d.items.length+'</b> records · '+d.overdue+' overdue</span><span>Fictional samples are marked</span></div></section>';
  $("#new-rfq")?.addEventListener("click",newRfqModal);$("#to-history").onclick=()=>loadView("history");
  $("#rfq-body").addEventListener("click",e=>{const owner=e.target.closest("[data-owner-rfq]");if(owner){e.stopPropagation();assignOwner(Number(owner.dataset.ownerRfq));return}const tr=e.target.closest("[data-rfq]");if(tr)rfqDetail(Number(tr.dataset.rfq))});
  let timer;async function filter(){const q=new URLSearchParams({q:$("#rfq-filter").value,status:$("#status-filter").value});const x=await api("/rfqs?"+q);$("#rfq-body").innerHTML=x.items.map(row).join("")||'<tr><td colspan="8" class="table-empty">No matching RFQs.</td></tr>'}
  $("#rfq-filter").oninput=()=>{clearTimeout(timer);timer=setTimeout(filter,220)};$("#status-filter").onchange=filter;
}
async function assignOwner(rfqId){
  try{
    const d=await api("/users/estimators");
    const options=d.items.map(x=>'<option value="'+x.id+'">'+esc(x.display_name)+'</option>').join("");
    showModal("Reassign RFQ owner","Choose an active estimator to own this RFQ.",'<div class="field"><label for="owner-choice">Estimator</label><select id="owner-choice">'+options+'</select></div>','<button class="button" data-close>Cancel</button><button class="button button-primary" id="save-owner">Save owner</button>');
    $("#modal-root [data-close]").onclick=closeModal;
    $("#save-owner").onclick=async()=>{try{await api("/rfqs/"+rfqId+"/owner",{method:"PATCH",body:JSON.stringify({owner_id:Number($("#owner-choice").value)})});closeModal();toast("RFQ owner updated.","success");renderOverview()}catch(e){toast(e.message,"error")}}
  }catch(e){toast(e.message,"error")}
}
async function rfqDetail(id){
  try{
    const r=await api("/rfqs/"+id),latest=r.revisions.sort((a,b)=>b.revision_number-a.revision_number)[0];
    let body=r.synthetic?banner("Fictional sample; not Company A history."):('<div class="note-box">'+esc(r.source_label)+"</div>");
    body+='<div class="form-grid" style="margin:14px 0"><div class="note-box">Due date<br/><b>'+dfmt(r.due_date)+'</b></div><div class="note-box">Owner<br/><b>'+esc(r.owner)+'</b></div></div>';
    body+='<div class="panel-title" style="margin:17px 0 8px">Parts · '+r.parts.length+'</div><div class="table-wrap"><table class="data-table"><thead><tr><th>Part</th><th>Material</th><th>Gross wt.</th><th>Annual volume</th><th>Cycle</th></tr></thead><tbody>'+r.parts.map(p=>'<tr><td>'+esc(p.part_name)+'</td><td>'+esc(p.material)+'</td><td>'+nfmt(p.gross_weight_kg)+' kg</td><td>'+nfmt(p.annual_volume,0)+'</td><td>'+nfmt(p.cycle_time_min)+' min</td></tr>').join("")+'</tbody></table></div>';
    if(r.sources?.length)body+='<div class="panel-title" style="margin:17px 0 8px">Source documents · '+r.sources.length+'</div><div class="stack">'+r.sources.map(s=>'<a class="source-document" href="'+esc(s.download_url)+'"><span>▤</span><span><b>'+esc(s.filename)+'</b><small>'+nfmt(s.size_bytes/1024,0)+' KB · '+esc(s.extraction_method||"saved")+(s.extraction_error?" · extraction needs review":"")+'</small></span><strong>Download ↓</strong></a>').join("")+'</div>';
    if(r.loss_reason)body+='<div class="note-box warn" style="margin-top:12px">Lost reason: '+esc(r.loss_reason)+"</div>";
    let footer='<button class="button" data-close>Close</button>';
    if(state.user.role==="sales"||(state.user.role==="estimator"&&r.owner_id===state.user.id))footer+='<button class="button" id="edit-rfq-header">Edit RFQ details</button>';
    if(state.user.role==="estimator"&&["estimating","returned"].includes(r.status))footer+='<button class="button button-primary" id="detail-cost">Open costing →</button>';
    if(["approved","sent","won","lost"].includes(r.status)&&latest&&["approved","sent"].includes(latest.status))footer+='<button class="button" id="download-pdf">Download approved PDF</button>';
    if(state.user.role==="sales"&&r.status==="approved"&&latest&&latest.status==="approved")footer+='<button class="button button-primary" id="mark-sent">Mark sent after dispatch</button>';
    if(state.user.role==="sales"&&r.status==="sent")footer+='<button class="button" id="mark-lost">Record lost</button><button class="button button-primary" id="mark-won">Record won</button>';
    showModal(r.rfq_number,r.customer+" · "+statusName(r.status),body,footer,true);
    $("#edit-rfq-header")?.addEventListener("click",()=>editRfqHeader(r));
    $("#detail-cost")?.addEventListener("click",()=>{state.selectedRfq=id;closeModal();loadView("costing")});
    $("#download-pdf")?.addEventListener("click",()=>downloadPdf(latest.id));
    $("#mark-sent")?.addEventListener("click",()=>markSent(latest.id));
    $("#mark-won")?.addEventListener("click",()=>recordOutcome(id,"won"));
    $("#mark-lost")?.addEventListener("click",()=>recordOutcome(id,"lost"));
  }catch(e){toast(e.message,"error")}
}
function editRfqHeader(r){
  const body='<form id="rfq-header-form"><div class="form-grid"><div class="field"><label>RFQ number</label><input name="rfq_number" maxlength="80" required value="'+esc(r.rfq_number)+'"/></div><div class="field"><label>Customer</label><input name="customer" maxlength="180" required value="'+esc(r.customer)+'"/></div><div class="field"><label>Due date</label><input name="due_date" type="date" required value="'+esc(r.due_date)+'"/></div></div></form>';
  showModal("Edit RFQ details","Header changes are recorded in the audit trail.",body,'<button class="button" data-close>Cancel</button><button class="button button-primary" id="save-rfq-header">Save changes</button>');
  $("#modal-root [data-close]").onclick=closeModal;
  $("#save-rfq-header").onclick=async()=>{const form=$("#rfq-header-form");if(!form.reportValidity())return;const data=Object.fromEntries(new FormData(form));try{await api("/rfqs/"+r.id,{method:"PATCH",body:JSON.stringify(data)});closeModal();toast("RFQ details updated.","success");rfqDetail(r.id)}catch(e){toast(e.message,"error")}}
}
async function downloadPdf(id){
  try{const res=await fetch("/api/revisions/"+id+"/pdf",{credentials:"same-origin"});if(!res.ok){const d=await res.json();throw new Error(d.detail||"PDF could not be generated")}const blob=await res.blob(),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download="approved-quote.pdf";a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);toast("Approved PDF downloaded. Record sent after dispatch.","success")}catch(e){toast(e.message,"error")}
}
async function markSent(id){
  confirmModal({
    title:"Mark quote as dispatched",
    subtitle:"Commercial quote transmission",
    message:"Have you manually dispatched the approved PDF to the customer? This records the transmission timestamp and transitions the RFQ to <strong>Sent</strong> status.",
    confirmText:"Mark as Sent",
    confirmClass:"button-primary",
    onConfirm:async()=>{
      try{
        await api("/revisions/"+id+"/sent",{method:"POST",body:"{}"});
        closeModal();
        toast("Quote marked sent.","success");
        loadView("overview");
      }catch(e){toast(e.message,"error")}
    }
  });
}
async function recordOutcome(id,decision){
  if(decision==="lost"){
    const body='<div class="field"><label>Reason for loss <span style="color:#c0392b">*</span></label><textarea id="outcome-lost-reason" maxlength="1000" placeholder="e.g. Competitor pricing, lead time constraint, specification shift…" style="min-height:90px"></textarea></div><div class="note-box warn" style="margin-top:10px">Recording as lost will close this RFQ lifecycle.</div>';
    const footer='<button class="button" data-close>Cancel</button><button class="button button-danger" id="outcome-submit-btn">Record as Lost</button>';
    showModal("Record RFQ outcome as Lost","Reason required for commercial tracking",body,footer);
    $("#modal-root [data-close]").onclick=closeModal;
    $("#outcome-submit-btn").onclick=async()=>{
      const reason=$("#outcome-lost-reason").value.trim();
      if(!reason)return toast("A reason for loss is required.","error");
      closeModal();
      try{
        await api("/rfqs/"+id+"/outcome",{method:"POST",body:JSON.stringify({decision:"lost",reason})});
        toast("Outcome recorded.","success");
        loadView("overview");
      }catch(e){toast(e.message,"error")}
    };
  }else{
    confirmModal({
      title:"Record RFQ outcome as Won",
      subtitle:"Commercial win confirmation",
      message:"Record this RFQ as <strong>Won</strong>? This will update the win/loss status in the register.",
      confirmText:"Record as Won",
      confirmClass:"button-primary",
      onConfirm:async()=>{
        try{
          await api("/rfqs/"+id+"/outcome",{method:"POST",body:JSON.stringify({decision:"won",reason:""})});
          toast("Outcome recorded.","success");
          loadView("overview");
        }catch(e){toast(e.message,"error")}
      }
    });
  }
}
async function newRfqModal(){
  if(!state.rates.length){try{state.rates=(await api("/rates")).items}catch{}}
  state.acceptedSources={};
  state.stagedSourceIds=[];
  const machine=(state.rates.filter(x=>x.rate_type==="machine").map(x=>x.rate_key)).filter((x,i,a)=>a.indexOf(x)===i);
  const partRow=(values={})=>`<div class="intake-part-row"><div class="section-heading">Part <span class="part-index"></span><button type="button" class="text-button remove-intake-part" style="float:right">Remove</button></div><div class="form-grid"><div class="field"><label>Part name</label><input data-part-field="part_name" value="${esc(values.part_name||"")}" required/></div><div class="field"><label>Material</label><input data-part-field="material" value="${esc(values.material||"")}" required/></div><div class="field"><label>Gross weight (kg)</label><input data-part-field="gross_weight_kg" type="number" min=".01" step=".01" value="${esc(values.gross_weight_kg||"")}" required/></div><div class="field"><label>Annual volume</label><input data-part-field="annual_volume" type="number" min="1" step="1" value="${esc(values.annual_volume||"")}" required/></div><div class="field"><label>Cycle time (minutes)</label><input data-part-field="cycle_time_min" type="number" min="0" step=".1" value="${esc(values.cycle_time_min||"")}" required/></div><div class="field"><label>Machine rate key</label><select data-part-field="machine_rate_key" required><option value="">Choose a rate</option>${machine.map(k=>`<option ${k===values.machine_rate_key?"selected":""}>${esc(k)}</option>`).join("")}${values.machine_rate_key&&!machine.includes(values.machine_rate_key)?`<option selected>${esc(values.machine_rate_key)}</option>`:""}</select></div></div></div>`;
  const body='<form id="new-form"><div class="form-grid"><div class="field"><label>RFQ number</label><input name="rfq_number" required placeholder="e.g. RFQ-2611-024"/></div><div class="field"><label>Customer</label><input name="customer" required/></div><div class="field"><label>Due date</label><input name="due_date" type="date" required/></div></div><div class="divider"></div><div class="section-heading">Parts in this RFQ</div><div id="intake-parts">'+partRow()+'</div><button class="button button-small" id="add-intake-part" type="button">＋ Add another part</button><div class="divider"></div><div class="section-heading">Optional source file</div><div class="intake-drop"><strong>Attach email, XLSX list, or drawing</strong><small>Original file retained with the RFQ · 12 MB max</small><input id="intake-file" type="file" accept=".txt,.eml,.csv,.xlsx,.pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp" style="display:block;margin:12px auto;font-size:10px"/><label style="font-size:9px"><input id="demo-file-ok" type="checkbox"/> This file contains synthetic demo data only and may be sent to the configured AI gateway.</label><br/><button class="button button-small" id="extract-file" type="button">✳ Extract suggestions</button></div><div id="suggestion-list" style="margin-top:10px"></div></form>';
  showModal("Start an RFQ","Enter known details; review any suggestions before applying.",body,'<button class="button" data-close>Cancel</button><button class="button button-primary" id="create-rfq">Create RFQ</button>',true);
  const refreshPartIndexes=()=>{$$(".intake-part-row").forEach((row,i)=>row.querySelector(".part-index").textContent=i+1)};
  const addPart=(values={})=>{$("#intake-parts").insertAdjacentHTML("beforeend",partRow(values));refreshPartIndexes()};
  $("#modal-root [data-close]").onclick=closeModal;$("#extract-file").onclick=extractFile;refreshPartIndexes();
  $("#intake-file").onchange=()=>{state.stagedSourceIds=[];state.acceptedSources={};$("#suggestion-list").innerHTML=""};
  $("#add-intake-part").onclick=()=>addPart();
  $("#intake-parts").onclick=e=>{const remove=e.target.closest(".remove-intake-part");if(!remove)return;if($$(".intake-part-row").length<=1)return toast("An RFQ needs at least one part.","error");remove.closest(".intake-part-row").remove();refreshPartIndexes()};
  $("#create-rfq").onclick=async()=>{const form=$("#new-form");if(!form.reportValidity())return;const metadata=Object.fromEntries(new FormData(form));const parts=$$(".intake-part-row").map(row=>{const part={};row.querySelectorAll("[data-part-field]").forEach(input=>part[input.dataset.partField]=input.value.trim());["gross_weight_kg","annual_volume","cycle_time_min"].forEach(k=>part[k]=Number(part[k]));part.source_ref=row.dataset.sourceRef||null;return part});try{const file=$("#intake-file").files[0];if(file&&!state.stagedSourceIds.length){const data=new FormData();data.append("file",file);data.append("demo_only",$("#demo-file-ok").checked?"true":"false");const staged=await api("/intake/file-extract",{method:"POST",body:data});state.stagedSourceIds.push(staged.file_id);if(staged.extraction_error)toast("File retained; extraction needs manual review.","error")}const sourceRef=Object.keys(state.acceptedSources).length?JSON.stringify(state.acceptedSources):null;const created=await api("/rfqs",{method:"POST",body:JSON.stringify({rfq_number:metadata.rfq_number,customer:metadata.customer,due_date:metadata.due_date,parts,source_ref:sourceRef,source_file_ids:state.stagedSourceIds})});closeModal();toast(`RFQ created with ${created.part_count} part${created.part_count===1?"":"s"} and ${created.sources?.length||0} source file${created.sources?.length===1?"":"s"}.`,"success");state.selectedRfq=created.id;loadView("overview")}catch(e){toast(e.message,"error")}}
}
async function extractFile(){
  const f=$("#intake-file").files[0];if(!f)return toast("Choose a file first.","error");
  const data=new FormData();data.append("file",f);data.append("demo_only",$("#demo-file-ok").checked?"true":"false");
  try{const d=await api("/intake/file-extract",{method:"POST",body:data});renderSuggestions(d)}catch(e){$("#suggestion-list").innerHTML='<div class="note-box warn">'+esc(e.message)+"</div>"}
}
function renderSuggestions(d){
  const map={rfq_number:"rfq_number",customer:"customer",due_date:"due_date",part_name:"part_name",material:"material",gross_weight_kg:"gross_weight_kg",annual_volume:"annual_volume",cycle_time_min:"cycle_time_min",machine_rate:"machine_rate_key"};
  if(d.file_id&&!state.stagedSourceIds.includes(d.file_id))state.stagedSourceIds.push(d.file_id);
  $("#suggestion-list").innerHTML='<div class="note-box '+(d.ai_used?"":"warn")+'">'+(d.ai_used?"Claude model suggestions · review required":"Pattern suggestions · AI did not run")+' · '+esc(d.method||"text")+' · '+esc(d.note)+(d.extraction_error?" · "+esc(d.extraction_error):"")+'</div>'+(d.parts?.length?'<div class="section-heading" style="margin-top:12px">Part rows found · accept each row to add it</div>'+d.parts.map((part,i)=>'<div class="suggestion-row"><strong>'+esc(part.values.part_name||"Part row")+'</strong><div>'+esc(Object.entries(part.values).map(([k,v])=>k.replaceAll("_"," ")+": "+v).join(" · "))+'<div class="suggestion-source">Source row: '+esc(part.source.excerpt)+'</div></div><div class="suggestion-actions"><button class="accept" data-part-accept="'+i+'">Add part</button></div></div>').join(""):'')+(d.fields?.length?d.fields.map((f,i)=>'<div class="suggestion-row"><strong>'+esc(f.name.replaceAll("_"," "))+'</strong><div>'+esc(f.value)+'<div class="suggestion-source">Source: '+esc(f.source?.excerpt||f.source?.file||"source")+'</div></div><div class="suggestion-actions"><button class="accept" data-accept="'+i+'">Accept</button><button data-reject="'+i+'">Reject</button></div></div>').join(""):'<div class="note-box">No field suggestions found. The original document is retained; enter details manually.</div>');
  $("#suggestion-list").dataset.fields=JSON.stringify(d.fields);
  $("#suggestion-list").dataset.parts=JSON.stringify(d.parts||[]);
  $$("[data-accept]").forEach(b=>b.onclick=()=>{const f=JSON.parse($("#suggestion-list").dataset.fields)[Number(b.dataset.accept)],name=map[f.name],input=name==="rfq_number"||name==="customer"||name==="due_date"?$("#new-form [name="+name+"]"):$(".intake-part-row [data-part-field="+name+"]");if(input){if(input.tagName==="SELECT"&&![...input.options].some(o=>o.value===f.value))input.add(new Option(f.value,f.value));input.value=f.value;b.textContent="Accepted";b.disabled=true;state.acceptedSources[f.name]={value:f.value,source:f.source,disposition:"accepted"};if(input.closest(".intake-part-row"))input.closest(".intake-part-row").dataset.sourceRef=JSON.stringify(state.acceptedSources)}else toast("Review this value; it is not a form field.","error")});
  $$("[data-reject]").forEach(b=>b.onclick=()=>{const f=JSON.parse($("#suggestion-list").dataset.fields)[Number(b.dataset.reject)];state.acceptedSources[f.name]={value:f.value,source:f.source,disposition:"rejected"};b.textContent="Rejected";b.disabled=true;b.previousElementSibling.disabled=true});
  $$("[data-part-accept]").forEach(b=>b.onclick=()=>{const part=JSON.parse($("#suggestion-list").dataset.parts)[Number(b.dataset.partAccept)];let rows=$$(".intake-part-row"),row=rows.length===1&&rows[0].querySelector('[data-part-field="part_name"]').value===""?rows[0]:null;if(!row){$("#add-intake-part").click();row=$$(".intake-part-row").at(-1)}Object.entries(part.values).forEach(([key,value])=>{const input=row.querySelector('[data-part-field="'+key+'"]');if(input){if(input.tagName==="SELECT"&&![...input.options].some(o=>o.value===value))input.add(new Option(value,value));input.value=value}});row.dataset.sourceRef=JSON.stringify({source:part.source,disposition:"accepted"});b.textContent="Added";b.disabled=true});
}

async function renderCosting(){
  const d=await api("/rfqs");state.rfqs=d.items.filter(x=>["estimating","returned"].includes(x.status));
  if(!state.rates.length)state.rates=(await api("/rates")).items;
  const preferred=state.rfqs.find(x=>x.id===state.selectedRfq)||state.rfqs[0];
  const options=state.rfqs.map(r=>'<option value="'+r.id+'" '+(preferred&&preferred.id===r.id?"selected":"")+'>'+esc(r.rfq_number)+" · "+esc(r.customer)+"</option>").join("");
  $("#view-root").innerHTML=heading("ESTIMATION","Costing workspace","Cost drivers stay editable. All prices use fixed formulas and dated rates.",state.user.role==="estimator"?'<button class="button" id="cost-new">＋ New RFQ</button>':"")+banner()+'<div class="content-grid costing-layout"><div class="stack"><section class="panel"><div class="panel-head"><div><div class="panel-title">Part cost build</div><span class="panel-subtitle">Select an estimating RFQ and review the inputs</span></div><select class="filter-select" id="cost-select">'+options+'</select></div><div id="cost-editor"></div></section><section class="panel"><div class="panel-head"><div><div class="panel-title">Calculated quote</div><span class="panel-subtitle">Prices before GST; no GST rate is configured in this demo.</span></div><span id="calc-state" class="demo-badge">NOT CALCULATED</span></div><div id="calc-result" class="empty-state"><div class="empty-icon">₹</div><strong>Costing is ready</strong><p>Enter volume points and calculate to create a quote revision.</p></div></section></div><aside class="stack"><section class="assistant-card"><header class="assistant-head"><span class="ai-mark">✳</span><div><strong>Quote assistant</strong><small>RFQ facts · past part retrieval</small></div><span class="ai-state" id="ai-state">Checking…</span></header><div class="assistant-body"><p class="assistant-intro">Ask about this RFQ or similar parts. Answers cite source records. The assistant never prices or approves.</p><div class="assistant-unavailable" id="ai-warning">Checking AI configuration…</div><div class="assistant-messages" id="messages"><div class="chat-message">Ask a source-grounded question. Synthetic results are labeled.</div></div><form class="assistant-input" id="assistant-form"><input id="assistant-question" maxlength="1000" placeholder="Ask about this RFQ…" autocomplete="off"/><button type="submit" id="assistant-send-btn" aria-label="Send" title="Send question">↑</button><button type="button" id="assistant-stop-btn" class="assistant-btn-stop" style="display:none" aria-label="Stop AI" title="Stop AI response">■ Stop</button></form></div></section><section class="panel"><div class="panel-head"><div><div class="panel-title">Pricing guardrails</div><span class="panel-subtitle">Applied to every estimate</span></div></div><div class="form-section"><div class="note-box">• Effective-dated rates<br/>• Immutable quote snapshots<br/>• Above ₹25 lakh: Sales Head approval required<br/>• AI never calculates cost</div></div></aside></div>';
  $("#cost-new")?.addEventListener("click",newRfqModal);if(preferred)await loadCostEditor(preferred.id);$("#cost-select").onchange=e=>{state.selectedRfq=Number(e.target.value);loadCostEditor(state.selectedRfq)};
  $("#assistant-form").onsubmit=sendAssistant;$("#assistant-stop-btn").onclick=stopAssistant;checkAI();
}
async function loadCostEditor(id){
  if(!id){$("#cost-editor").innerHTML='<div class="empty-state"><div class="empty-icon">◫</div><strong>No RFQs ready for costing</strong><p>Create one or select an estimating RFQ.</p></div>';return}
  try{
    const r=await api("/rfqs/"+id);state.selectedRfq=id;
    const machines=[...new Set(state.rates.filter(x=>x.rate_type==="machine").map(x=>x.rate_key))];
    const partMarkup=p=>{const ops=p.routing_operations?.length?p.routing_operations:[{operation_name:"Primary operation",machine_rate_key:p.machine_rate_key,cycle_time_min:p.cycle_time_min}];return `<div class="form-section cost-part" data-part="${p.id}"><div class="section-heading">${esc(p.part_name)} <span class="helper">${esc(p.material)}</span></div><div class="form-grid">${field("Gross weight (kg)","gross_weight_kg",p.gross_weight_kg,"number",".01")}${field("Annual volume","annual_volume",p.annual_volume,"number","1")}${field("Scrap (%)","scrap_pct",p.scrap_pct,"number",".1")}${field("Margin markup (%)","margin_pct",p.margin_pct,"number",".1")}${field("Overhead / part (₹)","overhead_per_part",p.overhead_per_part,"number",".01")}${field("Freight / part (₹)","freight_per_part",p.freight_per_part,"number",".01")}${field("Packing / part (₹)","packing_per_part",p.packing_per_part,"number",".01")}</div><div class="route-editor"><div class="section-heading">Routing operations <span class="helper">Ordered steps · rate and cycle time per step</span></div><div class="route-operations">${ops.map((op,i)=>routeOperationMarkup(op,machines,i)).join("")}</div><button class="button button-small" type="button" data-add-operation>＋ Add operation</button></div><div class="helper" style="margin-top:9px">Source: ${esc(p.source_ref||r.source_label)} · rates are captured when calculated.</div></div>`};
    const vol=r.parts[0]?.annual_volume||10000;
    const v1=Math.max(100,vol>=20000?Math.round(vol/10000)*1000:Math.max(1,Math.round(vol*0.25)));
    const v2=Math.max(v1+100,vol>=20000?Math.round(vol/2/1000)*1000:Math.max(v1+1,Math.round(vol*0.5)));
    const v3=Math.max(v2+100,vol);
    const defaultVols=[v1,v2,v3];
    const scenarioMarkup=[1,2,3].map(i=>`<div class="field"><label>${i===3?"Customer annual volume":"Scenario "+i+" · units/year"}</label><input id="volume-${i}" type="number" min="1" value="${defaultVols[i-1]}"/></div>`).join("");
    $("#cost-editor").innerHTML=`<div class="form-section"><div class="section-heading">${esc(r.rfq_number)} <span class="demo-badge">${r.synthetic?"SYNTHETIC DEMO":"PROVIDED SAMPLE"}</span></div><div class="form-grid"><div class="note-box">Customer<br/><b>${esc(r.customer)}</b></div><div class="note-box">Due date<br/><b>${dfmt(r.due_date)}</b></div></div></div>${r.parts.map(partMarkup).join("")}<div class="form-section"><div class="section-heading">Volume scenarios</div><div class="scenario-grid">${scenarioMarkup}</div><div class="helper" style="margin-top:8px">Approval value uses the highest scenario in this preview. Confirm annual volume before submitting.</div></div><div class="form-section" style="display:flex;justify-content:flex-end"><button class="button button-primary" id="calculate">Calculate & save revision →</button></div>`;
    $$(".cost-part").forEach(row=>wireRoutingEditor(row,machines));
    wireRouteSuggestions();
    $("#calculate").onclick=()=>calculateQuote(id);
  }catch(e){toast(e.message,"error")}
}
function routeOperationMarkup(op,machines,index){const keys=[...machines];if(op.machine_rate_key&&!keys.includes(op.machine_rate_key))keys.push(op.machine_rate_key);return `<div class="route-operation"><span class="route-sequence">${index+1}</span><div class="field"><label>Operation</label><input name="operation_name" maxlength="120" value="${esc(op.operation_name||"")}" placeholder="e.g. Turning"/></div><div class="field"><label>Machine rate</label><select name="operation_rate">${keys.map(k=>`<option ${k===op.machine_rate_key?"selected":""}>${esc(k)}</option>`).join("")}</select></div><div class="field"><label>Cycle (min)</label><input name="operation_cycle" type="number" min="0" step=".1" value="${esc(op.cycle_time_min)}"/></div><button type="button" class="text-button" data-remove-operation>Remove</button></div>`}
function wireRoutingEditor(row,machines){const list=row.querySelector(".route-operations");row.querySelector("[data-add-operation]").onclick=()=>{list.insertAdjacentHTML("beforeend",routeOperationMarkup({operation_name:"",machine_rate_key:machines[0]||"",cycle_time_min:0},machines,list.querySelectorAll(".route-operation").length))};list.addEventListener("click",e=>{const button=e.target.closest("[data-remove-operation]");if(!button)return;if(list.querySelectorAll(".route-operation").length<=1)return toast("A part needs at least one routing operation.","error");button.closest(".route-operation").remove();list.querySelectorAll(".route-operation").forEach((x,i)=>x.querySelector(".route-sequence").textContent=i+1)})}
function wireRouteSuggestions(){
  state.routeSuggestions={};
  $$(".cost-part").forEach(row=>{
    const title=row.querySelector(".section-heading"),button=document.createElement("button");
    button.className="text-button";button.type="button";button.textContent="Find similar routing";
    title.append(" ",button);
    const output=document.createElement("div");output.className="routing-results";row.append(output);
    button.onclick=async()=>{
      output.innerHTML='<div class="helper">Searching past parts…</div>';
      try{
        const d=await api("/parts/"+row.dataset.part+"/routing-suggestions");state.routeSuggestions[row.dataset.part]=d.items;
        if(!d.items.length){output.innerHTML='<div class="note-box" style="margin-top:8px">No comparable historic route was found. Enter routing manually.</div>';return}
        output.innerHTML='<div class="note-box" style="margin-top:8px">'+esc(d.method||"Historical route suggestions")+' · estimator acceptance required</div>'+(d.warning?'<div class="note-box warn" style="margin-top:8px">'+esc(d.warning)+'</div>':"")+d.items.map((x,i)=>{const routeText=x.operations?.map(op=>`${op.operation_name} · ${op.machine_rate_key} · ${nfmt(op.cycle_time_min)} min`).join(" → ")||`${x.part_name} · ${x.material} · ${nfmt(x.cycle_time_min)} min`;return '<div class="suggestion-row"><strong>'+esc(x.operations?.length?x.operations.length+" steps":x.routing_key||"Historical route")+'</strong><div>'+esc(routeText)+'<br/><span class="suggestion-source">Source '+esc(x.rfq_number)+' · '+esc(x.source_label)+(x.synthetic?" · SYNTHETIC DEMO":"")+'</span><div class="helper">'+esc(x.suggestion||"")+'</div></div><div class="suggestion-actions"><button class="accept" data-route-accept="'+i+'">Use suggestion</button></div></div>'}).join("");
        $$("[data-route-accept]",output).forEach(accept=>accept.onclick=()=>{
          const x=state.routeSuggestions[row.dataset.part][Number(accept.dataset.routeAccept)];
          const routes=x.operations?.length?x.operations:[{operation_name:"Primary operation",machine_rate_key:x.routing_key,cycle_time_min:x.cycle_time_min}];
          row.querySelector(".route-operations").innerHTML=routes.map((op,index)=>routeOperationMarkup(op,[...new Set(state.rates.filter(rate=>rate.rate_type==="machine").map(rate=>rate.rate_key))],index)).join("");
          row.dataset.routingSource="Routing candidate from "+x.rfq_number+" · "+x.part_name;
          accept.textContent="Accepted";accept.disabled=true;
          toast("Routing suggestion accepted; verify it before quoting.","success");
        });
      }catch(e){output.innerHTML='<div class="note-box warn">'+esc(e.message)+"</div>"}
    };
  });
}
function field(label,name,value,type="number",step="any"){return '<div class="field"><label>'+label+'</label><input name="'+name+'" type="'+type+'" min="0" step="'+step+'" value="'+esc(value)+'"/></div>'}
async function calculateQuote(id){
  try{
    for(const row of $$(".cost-part")){const data={};["gross_weight_kg","annual_volume","scrap_pct","margin_pct","overhead_per_part","freight_per_part","packing_per_part"].forEach(k=>{data[k]=Number(row.querySelector(`[name="${k}"]`).value)});data.routing_operations=[...row.querySelectorAll(".route-operation")].map(op=>({operation_name:op.querySelector('[name="operation_name"]').value.trim(),machine_rate_key:op.querySelector('[name="operation_rate"]').value,cycle_time_min:Number(op.querySelector('[name="operation_cycle"]').value)}));if(row.dataset.routingSource)data.source_ref=row.dataset.routingSource;await api("/parts/"+row.dataset.part,{method:"PATCH",body:JSON.stringify(data)})}
    const volumes=[1,2,3].map(i=>Number($("#volume-"+i).value)).filter(Boolean);const q=await api("/rfqs/"+id+"/cost",{method:"POST",body:JSON.stringify({volumes})});state.quote=q;renderQuoteCalc(q);toast("Revision saved with rate snapshots.","success")
  }catch(e){toast(e.message,"error")}
}
function renderQuoteCalc(q){
  $("#calc-state").className="status-pill status-estimating";$("#calc-state").textContent="Revision "+q.revision_number+" · Draft";
  const vols=q.breakdown[0].scenarios.map(x=>x.volume);
  let rows="";
  q.breakdown.forEach(line=>{
    rows+='<tr><td class="line-title">'+esc(line.part_name)+'<br/><small>'+esc(line.material)+'</small></td>'+line.scenarios.map(s=>'<td class="amount">'+money(s.unit_cost)+'<br/><small>sell '+money(s.unit_price)+'</small></td>').join("")+"</tr>";
    ["material","processing","overhead","freight","packing"].forEach(k=>{
      rows+='<tr><td>'+({material:"Material",processing:"Process",overhead:"Overhead",freight:"Freight",packing:"Packing"}[k])+"</td>"+line.scenarios.map(s=>'<td class="amount">'+money(s[k])+"</td>").join("")+"</tr>";
    });
  });
  const scenarioAnnual=vols.map(v=>q.breakdown.reduce((sum,l)=>sum+(l.scenarios.find(s=>s.volume===v)?.annual_value||0),0));
  rows+='<tr class="cost-total"><td>Annual quote value · before GST</td>'+scenarioAnnual.map(value=>'<td class="amount">'+money(value)+"</td>").join("")+"</tr>";
  rows+='<tr><td>GST ('+nfmt(q.gst_rate_percent||0,2)+'%) · shown separately</td>'+scenarioAnnual.map(value=>'<td class="amount">'+money(value*(q.gst_rate_percent||0)/100)+"</td>").join("")+"</tr>";
  rows+='<tr class="cost-total"><td>Annual value · including GST</td>'+scenarioAnnual.map(value=>'<td class="amount">'+money(value*(1+(q.gst_rate_percent||0)/100))+"</td>").join("")+"</tr>";
  const rateSummary=q.rate_snapshots.map(r=>esc(r.material_rate_key)+" ₹"+nfmt(r.material_rate)+"/kg · "+(r.operation_rates?.length?r.operation_rates.map(op=>esc(op.operation_name)+" · "+esc(op.machine_rate_key)+" ₹"+nfmt(op.rate_amount)+"/hr").join(" → "):esc(r.machine_rate_key)+" ₹"+nfmt(r.machine_rate)+"/hr")).join("; ");
  $("#calc-result").className="";$("#calc-result").innerHTML='<div class="table-wrap"><table class="cost-lines"><thead><tr><th>Part / component</th>'+vols.map(v=>'<th>'+nfmt(v,0)+' units<br/><small>₹ / part</small></th>').join("")+'</tr></thead><tbody>'+rows+'</tbody></table></div><div class="form-section" style="display:flex;justify-content:space-between;align-items:center"><div class="helper">Highest scenario: <b>'+money(q.annual_value)+'</b> · '+(q.annual_value>2500000?"Above ₹25 lakh approval gate":"Sales approval workflow applies")+'</div><button class="button button-primary" id="submit-quote">Send to Sales Head →</button></div><div class="form-section helper">Rate snapshots: '+rateSummary+"</div>";
  $("#submit-quote").onclick=async()=>{try{await api("/revisions/"+q.revision_id+"/submit",{method:"POST",body:"{}"});toast("Submitted for Sales Head approval.","success");loadView("overview")}catch(e){toast(e.message,"error")}}
}
async function checkAI(){try{const d=await api("/assistant/status");$("#ai-state").textContent=d.label;$("#ai-warning").textContent=!d.configured?"AI is not configured. Set AI_API_KEY privately; model answers will not be fabricated. Intake pattern suggestions remain available.":d.available?d.model+" responded successfully through the configured gateway. Customer data stays out of hosted inference unless NDA/no-training terms are approved.":(d.last_error||"AI is configured but has not passed a live response check.")+" No model result will be presented as successful; local extraction remains available."}catch(e){$("#ai-state").textContent="Unavailable";$("#ai-warning").textContent=e.message}}
let assistantController=null;

function renderMarkdown(raw){
  if(!raw)return"";
  raw=raw.replace(/\r\n/g,"\n").replace(/\r/g,"\n");
  raw=raw.replace(/\x60\x60\x60(?:markdown|md)?\s*([\s\S]*?)\x60\x60\x60/gi,"$1");
  raw=raw.replace(/(#{1,6}\s+[^|\n]+?)\s+(?=\|)/g,"$1\n");
  raw=raw.replace(/\s*\|\s*((?::?-{2,}:?\s*\|){2,})/g,"\n|$1\n");

  const escapeHtml=s=>String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");

  function formatCell(text){
    let s=escapeHtml(text);
    s=s.replace(/(?:\*\*)?synthetic demo[—\-\s]*not customer data(?:\*\*)?/gi,
      '<span class="demo-badge" style="display:inline-block;padding:2px 5px;border-radius:4px;font-size:8.5px;background:#fef3c7;color:#92400e;border:1px solid #fde68a;font-weight:600">SYNTHETIC DEMO</span>');
    s=s.replace(/\b((?:DEMO-)?RFQ-[A-Za-z0-9\-]+)\b/g,
      '<code style="background:#eef3f0;padding:2px 5px;border-radius:4px;color:#1e4b37;font-weight:600">$1</code>');
    s=s.replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>");
    s=s.replace(/\*([^\*]+?)\*/g,"<em>$1</em>");
    s=s.replace(/`([^`]+?)`/g,"<code>$1</code>");
    return s;
  }

  function formatInline(str){
    let s=escapeHtml(str);
    s=s.replace(/\b((?:DEMO-)?RFQ-[A-Za-z0-9\-]+)\b/g,
      '<code style="background:#eef3f0;padding:2px 5px;border-radius:4px;color:#1e4b37;font-weight:600">$1</code>');
    s=s.replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>");
    s=s.replace(/\*([^\*]+?)\*/g,"<em>$1</em>");
    s=s.replace(/`([^`]+?)`/g,"<code>$1</code>");
    return s;
  }

  const lines=raw.split("\n");
  let html="",inTable=false,inList=false,listType="";
  for(let i=0;i<lines.length;i++){
    const line=lines[i].trim();
    const hasPipes=(line.startsWith("|")&&line.endsWith("|"))||(line.split("|").length>=3);
    if(hasPipes){
      let content=line;
      if(content.startsWith("|"))content=content.slice(1);
      if(content.endsWith("|"))content=content.slice(0,-1);
      const cells=content.split("|").map(c=>c.trim());
      if(cells.every(c=>/^:?-+:?$/.test(c)))continue;
      if(!inTable){
        if(inList){html+="</"+listType+">";inList=false}
        inTable=true;
        html+='<div class="chat-table-wrap"><table class="chat-table"><thead><tr>';
        cells.forEach(c=>{html+='<th>'+formatInline(c)+'</th>'});
        html+='</tr></thead><tbody>';
      }else{
        const recordStarts=cells.reduce((indexes,cell,index)=>{if(/^(?:DEMO-)?RFQ-[A-Za-z0-9-]+$/i.test(cell))indexes.push(index);return indexes},[]);
        const rows=recordStarts.length>1
          ? recordStarts.map((start,index)=>cells.slice(start,recordStarts[index+1]??cells.length))
          : [cells];
        rows.forEach(row=>{html+='<tr>';row.forEach(c=>{html+='<td>'+formatCell(c)+'</td>'});html+='</tr>'});
      }
      continue;
    }else if(inTable){
      html+='</tbody></table></div>';
      inTable=false;
    }
    if(/^[\*\-]\s+/.test(line)){
      if(inTable){html+='</tbody></table></div>';inTable=false}
      if(!inList||listType!=="ul"){
        if(inList)html+="</"+listType+">";
        html+='<ul class="chat-list">';
        inList=true;listType="ul";
      }
      html+='<li>'+formatInline(line.replace(/^[\*\-]\s+/,""))+'</li>';
      continue;
    }
    if(/^\d+\.\s+/.test(line)){
      if(inTable){html+='</tbody></table></div>';inTable=false}
      if(!inList||listType!=="ol"){
        if(inList)html+="</"+listType+">";
        html+='<ol class="chat-list">';
        inList=true;listType="ol";
      }
      html+='<li>'+formatInline(line.replace(/^\d+\.\s+/,""))+'</li>';
      continue;
    }
    if(inList){html+="</"+listType+">";inList=false}
    if(/^###\s+/.test(line)){html+='<h4 class="chat-h">'+formatInline(line.replace(/^###\s+/,""))+'</h4>';continue}
    if(/^##\s+/.test(line)){html+='<h3 class="chat-h">'+formatInline(line.replace(/^##\s+/,""))+'</h3>';continue}
    if(/^#\s+/.test(line)){html+='<h3 class="chat-h">'+formatInline(line.replace(/^#\s+/,""))+'</h3>';continue}
    if(!line)continue;
    html+='<p class="chat-p">'+formatInline(line)+'</p>';
  }
  if(inTable)html+='</tbody></table></div>';
  if(inList)html+="</"+listType+">";
  return html;
}

function stopAssistant(){
  if(assistantController){
    assistantController.abort();
    assistantController=null;
    const box=$("#messages");
    box?.querySelector("[data-wait]")?.remove();
    box?.insertAdjacentHTML("beforeend",'<div class="chat-message stopped">Generation stopped by user.</div>');
    if(box)box.scrollTop=box.scrollHeight;
    resetAssistantForm();
  }
}

function resetAssistantForm(){
  const input=$("#assistant-question");
  const sendBtn=$("#assistant-send-btn");
  const stopBtn=$("#assistant-stop-btn");
  if(input){
    input.disabled=false;
    input.placeholder="Ask about this RFQ…";
    input.focus();
  }
  if(sendBtn)sendBtn.style.display="inline-flex";
  if(stopBtn)stopBtn.style.display="none";
}

async function sendAssistant(e){
  if(e)e.preventDefault();
  if(assistantController)return; // Block simultaneous inputs
  const input=$("#assistant-question");
  const q=input.value.trim();
  if(!q)return;
  const box=$("#messages");
  box.insertAdjacentHTML("beforeend",'<div class="chat-message user">'+esc(q)+'</div><div class="chat-message" data-wait>Checking source records…</div>');
  input.value="";
  input.disabled=true;
  input.placeholder="AI is answering…";
  const sendBtn=$("#assistant-send-btn");
  const stopBtn=$("#assistant-stop-btn");
  if(sendBtn)sendBtn.style.display="none";
  if(stopBtn)stopBtn.style.display="inline-flex";
  assistantController=new AbortController();
  try{
    const d=await api("/assistant/chat",{
      method:"POST",
      body:JSON.stringify({question:q,rfq_id:state.selectedRfq||null}),
      signal:assistantController.signal
    });
    box.querySelector("[data-wait]")?.remove();
    const formatted=renderMarkdown(d.answer);
    const sourcesHtml=d.sources.length?'<div class="chat-sources"><strong>Cited records:</strong><div class="chat-source-pills">'+d.sources.map(s=>'<span class="source-chip">'+esc(s.rfq_number)+" · "+esc(s.part_name||s.part||"part")+(s.synthetic?' <small style="color:#d97706">(SYNTHETIC)</small>':'')+'</span>').join("")+'</div></div>':'';
    box.insertAdjacentHTML("beforeend",'<div class="chat-message">'+formatted+sourcesHtml+'</div>');
  }catch(err){
    box.querySelector("[data-wait]")?.remove();
    if(err.name==="AbortError"){
      box.insertAdjacentHTML("beforeend",'<div class="chat-message stopped">Generation stopped by user.</div>');
    }else{
      box.insertAdjacentHTML("beforeend",'<div class="chat-message error">'+esc(err.message)+'<div class="chat-sources">No AI response was generated.</div></div>');
    }
  }finally{
    assistantController=null;
    resetAssistantForm();
    box.scrollTop=box.scrollHeight;
  }
}

async function renderRates(){
  state.rates=(await api("/rates")).items;const groups={material:[],machine:[]};state.rates.forEach(r=>groups[r.rate_type].push(r));
  $("#view-root").innerHTML=heading("MASTER DATA","Rate master","Every quote retains the dated rate versions it used.",state.user.role==="sales"?'<button class="button button-primary" id="add-rate">＋ Add rate version</button>':"")+banner("Fictional rate values make the demo costable. Replace before commercial use.")+'<div class="content-grid"><div class="stack">'+["material","machine"].map(k=>'<section class="panel"><div class="panel-head"><div><div class="panel-title">'+(k==="material"?"Material rates":"Machine-hour rates")+'</div><span class="panel-subtitle">'+groups[k].length+" dated versions</span></div><span class=\"demo-badge\">DEMO VALUES</span></div>"+groups[k].map(r=>'<div class="rate-version"><div><div class="rate-key">'+esc(r.rate_key)+'</div><div class="rate-unit">'+esc(r.unit)+" · from "+dfmt(r.effective_from)+(r.effective_to?" to "+dfmt(r.effective_to):" · current")+'</div></div><div class="rate-amount">'+money(r.amount)+'</div><span class="demo-badge">'+(r.synthetic?"SYNTHETIC":"LIVE")+"</span></div>").join("")+"</section>").join("")+'</div><aside class="panel"><div class="panel-head"><div><div class="panel-title">Rate governance</div><span class="panel-subtitle">Versioning rules</span></div></div><div class="form-section"><div class="note-box">• Effective date selects the rate.<br/>• Overlapping versions are rejected.<br/>• Past quote snapshots never change.<br/>• Demo values are not Company A rates.</div></div></aside></div>';
  $("#add-rate")?.addEventListener("click",rateModal)
}
function rateModal(){
  const body='<form id="rate-form"><div class="form-grid"><div class="field"><label>Rate type</label><select name="rate_type"><option value="material">Material</option><option value="machine">Machine hour</option></select></div><div class="field"><label>Rate key</label><input name="rate_key" required placeholder="e.g. EN8"/></div><div class="field"><label>Amount (₹)</label><input name="amount" type="number" min="0" step=".01" required/></div><div class="field"><label>Unit</label><select name="unit"><option>₹ / kg</option><option>₹ / hour</option></select></div><div class="field"><label>Effective from</label><input name="effective_from" type="date" required value="'+new Date().toISOString().slice(0,10)+'"/></div><div class="field"><label>Effective to · optional</label><input name="effective_to" type="date"/></div></div></form><div class="note-box warn" style="margin-top:12px">Use only client-approved commercial rates.</div>';
  showModal("Add a rate version","Create a non-overlapping effective period.",body,'<button class="button" data-close>Cancel</button><button class="button button-primary" id="save-rate">Save version</button>');
  const rateType=$("#rate-form [name=rate_type]"),unit=$("#rate-form [name=unit]");const syncUnit=()=>{unit.value=rateType.value==="material"?"₹ / kg":"₹ / hour"};rateType.addEventListener("change",syncUnit);syncUnit();
  $("#modal-root [data-close]").onclick=closeModal;$("#save-rate").onclick=async()=>{const f=$("#rate-form");if(!f.reportValidity())return;const d=Object.fromEntries(new FormData(f));d.amount=Number(d.amount);d.effective_to=d.effective_to||null;try{await api("/rates",{method:"POST",body:JSON.stringify(d)});closeModal();toast("Rate version saved.","success");loadView("rates")}catch(e){toast(e.message,"error")}}
}
async function renderApprovals(){
  const d=await api("/approvals");$("#approval-nav-count").textContent=d.items.length;
  let content=heading("COMMERCIAL REVIEW","Approvals","Review exact quote revision and rate snapshot before release.");
  content+=banner("Synthetic approvals are workflow examples only.");
  content+='<div class="content-grid"><section class="panel"><div class="panel-head"><div><div class="panel-title">Awaiting your decision</div><span class="panel-subtitle">'+d.items.length+' revisions in queue</span></div><span class="badge-amber">Sales Head</span></div><div class="form-section" id="approval-list">';
  content+=d.items.map(approvalCard).join("")||'<div class="empty-state"><div class="empty-icon">✓</div><strong>Approval queue is clear</strong><p>Submitted revisions appear here with costs and rate snapshots.</p></div>';
  content+='</div></section><aside class="stack"><section class="panel"><div class="panel-head"><div class="panel-title">Review checklist</div></div><div class="form-section"><div class="note-box">1. Check customer and part details.<br/>2. Review each volume/cost breakup.<br/>3. Confirm rate snapshots.<br/>4. Approve or return with reason.<br/>5. Download PDF; mark sent after dispatch.</div></div></section><section class="panel"><div class="form-section"><div class="section-heading">Threshold rule</div><div class="note-box warn">Above ₹25 lakh annual value requires approval. This demo sends all quotes through Sales Head review. Confirm threshold scope and GST basis.</div></div></section></aside></div>';
  $("#view-root").innerHTML=content;
  $("#approval-list").addEventListener("click",approvalClick)
}
function approvalCard(r){
  const high=r.annual_value>2500000;
  let s='<article class="approval-card"><div class="approval-top"><div><div class="approval-title">'+esc(r.rfq_number)+' · '+esc(r.customer)+(r.synthetic?' <span class="demo-badge">DEMO</span>':'')+'</div><div class="approval-meta">Revision '+r.revision_number+' · '+esc(r.owner)+' · '+new Date(r.created_at).toLocaleDateString("en-IN")+'</div></div><div class="approval-value">'+money(r.annual_value)+'</div></div>';
  if(high)s+='<div class="note-box warn" style="margin-top:10px">Above ₹25 lakh · approval gate applies</div>';
  s+='<div class="approval-lines">'+r.breakdown.map(l=>{const scenario=l.scenarios.reduce((best,item)=>item.volume>best.volume?item:best,l.scenarios[0]);return '<div class="approval-line"><span>'+esc(l.part_name)+' · '+esc(l.material)+'</span><span>'+money(scenario.unit_price)+' / part · '+nfmt(scenario.volume,0)+' units</span></div>'}).join("");
  s+='<div class="helper" style="margin-top:8px">Rates: '+r.rates.map(x=>esc(x.material_rate_key)+' ₹'+nfmt(x.material_rate)+'/kg · '+(x.operation_rates?.length?x.operation_rates.map(op=>esc(op.operation_name)+' · '+esc(op.machine_rate_key)+' ₹'+nfmt(op.rate_amount)+'/hr').join(" → "):esc(x.machine_rate_key)+' ₹'+nfmt(x.machine_rate)+'/hr')).join("; ")+'</div></div>';
  s+='<div class="approval-actions"><button class="button button-small" data-return="'+r.id+'">Return with reason</button><button class="button button-primary button-small" data-approve="'+r.id+'">Approve revision</button></div></article>';
  return s
}
async function approvalClick(e){
  const a=e.target.closest("[data-approve]"),r=e.target.closest("[data-return]");
  if(a){
    confirmModal({
      title:"Approve quote revision",
      subtitle:"Commercial release authorization",
      message:"Approve this exact revision? This locks the quote and snapshots all cost drivers. Any future edits will require a new approval revision.",
      confirmText:"Approve revision",
      confirmClass:"button-primary",
      onConfirm:()=>submitDecision(a.dataset.approve,"approve","")
    });
    return;
  }
  if(r){showModal("Return this revision","A reason is required and will be recorded.",'<div class="field"><label>Reason for return</label><textarea id="return-reason" maxlength="1000" placeholder="What needs to change?"></textarea></div>','<button class="button" data-close>Cancel</button><button class="button button-danger" id="confirm-return">Return to estimator</button>');$("#modal-root [data-close]").onclick=closeModal;$("#confirm-return").onclick=()=>{const reason=$("#return-reason").value.trim();if(!reason)return toast("Add a reason.","error");closeModal();submitDecision(r.dataset.return,"return",reason)}}
}
async function submitDecision(id,decision,reason){try{const d=await api("/revisions/"+id+"/decision",{method:"POST",body:JSON.stringify({decision,reason})});toast(decision==="approve"?"Quote approved.":"Returned with reason.","success");renderApprovals()}catch(e){toast(e.message,"error")}}

async function renderHistory(q=state.historyQuery||"",page=state.historyPage||1){
  state.historyRequest=(state.historyRequest||0)+1;const requestId=state.historyRequest;
  const d=await api("/history?q="+encodeURIComponent(q)+"&page="+page+"&page_size=25");if(requestId!==state.historyRequest)return;state.history=d.items;state.historyQuery=q;state.historyPage=d.page;
  const rows=d.items.map(h=>'<tr><td class="rfq-cell"><strong>'+esc(h.rfq_number)+'</strong><small>'+esc(h.customer)+'</small></td><td>'+esc(h.part_name)+'</td><td>'+esc(h.material)+'</td><td>'+(h.gross_weight_kg==null?"—":nfmt(h.gross_weight_kg)+" kg")+'</td><td>'+(h.annual_volume?nfmt(h.annual_volume,0):"—")+'</td><td class="amount">'+(h.quoted_unit_price==null?"—":money(h.quoted_unit_price))+'</td><td>'+(h.synthetic?'<span class="demo-badge">SYNTHETIC</span>':'<span class="status-pill status-historical">'+(h.record_type==="historical"?"Imported":"Provided sample")+"</span>")+"</td></tr>").join("");
  let html=heading("RETRIEVAL & MIGRATION","Quote history","Search similar parts; historical values are shown as supplied.",(state.user.role==="estimator"?'<button class="button button-primary" id="import-open">↥ Import Excel</button>':""));
  html+=banner("Synthetic matches are fictional; replace them with the approved workbook.");
  html+='<section class="panel"><div class="panel-head"><div><div class="panel-title">Find a comparable part</div><span class="panel-subtitle">Search part, material, RFQ, or customer</span></div><input class="filter-input" id="history-search" value="'+esc(q)+'" placeholder="Try EN8 or spindle"/></div>';
  html+='<div class="table-wrap"><table class="data-table"><thead><tr><th>RFQ / source</th><th>Part</th><th>Material</th><th>Gross wt.</th><th>Annual volume</th><th>Quoted unit price</th><th>Record</th></tr></thead><tbody>';
  html+=rows||'<tr><td colspan="7" class="table-empty"><strong>No matching quote history</strong>Try another search.</td></tr>';
  html+='</tbody></table></div><div class="table-footer"><span>Showing '+(d.total?((d.page-1)*d.page_size+1):0)+'–'+Math.min(d.page*d.page_size,d.total)+' of '+d.total+' records · source values preserved</span><span>'+d.items.filter(x=>x.synthetic).length+' synthetic rows on this page</span></div><div class="pagination"><button class="button button-small" id="history-prev" '+(d.page<=1?"disabled":"")+'>← Previous</button><span>Page '+d.page+' of '+Math.max(1,d.pages)+'</span><button class="button button-small" id="history-next" '+(d.page>=d.pages?"disabled":"")+'>Next →</button></div></section>';
  html+=state.user.role==="estimator"?'<section class="panel" style="margin-top:14px"><div class="panel-head"><div><div class="panel-title">Import past quotes</div><span class="panel-subtitle">XLSX · preview first · row-level validation</span></div><span class="count-chip">Client workbook not included</span></div><div class="form-section"><div class="helper">RFQ, customer, part, material, weight, volume, cycle time, unit price, annual value, and quote date are supported.</div><button class="button" style="margin-top:10px" id="import-open-2">Choose workbook</button></div></section>':"";
  $("#view-root").innerHTML=html;
  $("#import-open")?.addEventListener("click",importModal);$("#import-open-2")?.addEventListener("click",importModal);
  $("#history-prev").onclick=()=>renderHistory(q,d.page-1);$("#history-next").onclick=()=>renderHistory(q,d.page+1);
  let timer;$("#history-search").oninput=e=>{const value=e.target.value,position=e.target.selectionStart;clearTimeout(timer);timer=setTimeout(async()=>{await renderHistory(value,1);const next=$("#history-search");if(next){next.focus();next.setSelectionRange(position,position)}},250)}
}
function importModal(){
  showModal("Import past quotes","Map your workbook columns, then review rows before importing.",'<div class="intake-drop"><strong>Choose Excel workbook</strong><small>XLSX · maximum 12 MB · original values are preserved</small><input id="xlsx" type="file" accept=".xlsx" style="display:block;margin:12px auto"/></div><label class="synthetic-import"><input id="force-synthetic" type="checkbox"/> Mark every row as synthetic demo data</label><div id="import-result" style="margin-top:12px"></div>','<button class="button" data-close>Close</button>',true);$("#modal-root [data-close]").onclick=closeModal;
  const body=$(".modal-body");body.insertAdjacentHTML("beforeend",'<button class="button button-small" id="preview-xlsx" style="margin-top:10px">Read workbook columns</button>');
  $("#preview-xlsx").onclick=()=>previewImport()
}
async function previewImport(mapping=null,sheetName=""){
  const f=$("#xlsx").files[0];if(!f)return toast("Choose an .xlsx workbook.","error");const fd=new FormData();fd.append("file",f);
  if(mapping)fd.append("mapping",JSON.stringify(mapping));if(sheetName)fd.append("sheet_name",sheetName);fd.append("force_synthetic",$("#force-synthetic").checked?"true":"false");
  try{const d=await api("/imports/preview",{method:"POST",body:fd});if(d.needs_mapping){renderImportMapping(d);return}state.batch=d.batch_id;
    $("#import-result").innerHTML='<div class="demo-banner"><b>'+d.valid_count+" valid</b> · <b>"+d.error_count+" rejected</b><span class=\"banner-right\">"+d.source_rows+" source rows</span></div>"+(d.preview.some(x=>x.synthetic)?'<div class="note-box warn">Synthetic demo rows will keep their label in history.</div>':"")+(d.errors.length?'<div class="note-box warn" style="margin-bottom:10px">'+d.errors.map(x=>"Row "+x.row+": "+esc(x.reason)).join("<br/>")+"</div>":"")+'<div class="table-wrap"><table class="data-table"><thead><tr><th>Row</th><th>RFQ</th><th>Customer</th><th>Part</th><th>Material</th><th>Price</th><th>Record</th></tr></thead><tbody>'+d.preview.map(x=>'<tr><td>'+x.row+'</td><td>'+esc(x.rfq_number)+'</td><td>'+esc(x.customer)+'</td><td>'+esc(x.part_name)+'</td><td>'+esc(x.material)+'</td><td>'+(x.quoted_unit_price==null?"—":money(x.quoted_unit_price))+'</td><td>'+(x.synthetic?'<span class="demo-badge">SYNTHETIC</span>':'Historical')+"</td></tr>").join("")+"</tbody></table></div>"+(d.valid_count?'<div style="display:flex;justify-content:flex-end;margin-top:12px"><button class="button button-primary" id="commit-xlsx">Import '+d.valid_count+" valid rows</button></div>":"");
    $("#commit-xlsx")?.addEventListener("click",async()=>{try{const x=await api("/imports/"+state.batch+"/commit",{method:"POST",body:"{}"});closeModal();toast(x.message,"success");renderHistory()}catch(e){toast(e.message,"error")}})
  }catch(e){$("#import-result").innerHTML='<div class="note-box warn">'+esc(e.message)+"</div>"}
}
function renderImportMapping(data){
  const labels={rfq_number:"RFQ number",customer:"Customer",part_name:"Part name",material:"Material",gross_weight_kg:"Gross weight (kg)",annual_volume:"Annual volume",cycle_time_min:"Cycle time (min)",machine_rate:"Machine rate",quoted_unit_price:"Quoted unit price",quoted_annual_value:"Quoted annual value",quoted_at:"Quote date",routing_key:"Routing key",synthetic:"Synthetic flag"};
  const options='<option value="">Not in workbook</option>'+data.headers.map(h=>'<option value="'+h.index+'">'+esc(h.label)+'</option>').join("");
  $("#import-result").innerHTML=(data.sheets?.length>1?'<label class="column-map-row" style="margin:12px 0">Worksheet<select id="import-sheet">'+data.sheets.map(name=>'<option '+(name===data.sheet_name?"selected":"")+'>'+esc(name)+'</option>').join("")+'</select><small>Import one worksheet at a time; repeat for other tabs.</small></label>':"")+'<div class="note-box">Check the suggested column matches. Required fields are marked.</div><div class="column-map">'+data.fields.map(f=>'<label class="column-map-row"><span>'+esc(labels[f.key]||f.key)+(f.required?' <b>*</b>':"")+'</span><select data-map="'+esc(f.key)+'">'+options+'</select></label>').join("")+'</div><div style="display:flex;justify-content:flex-end;margin-top:12px"><button class="button button-primary" id="map-validate">Map columns and validate</button></div>';
  data.fields.forEach(f=>{const select=$("[data-map='"+f.key+"']");const suggested=data.suggested_mapping[f.key];if(suggested!==null&&suggested!==undefined)select.value=String(suggested)});
  $("#map-validate").onclick=()=>{const mapping={};$$('[data-map]').forEach(select=>{if(select.value!=="")mapping[select.dataset.map]=Number(select.value)});previewImport(mapping,$("#import-sheet")?.value||data.sheet_name||"")}
}

boot();
