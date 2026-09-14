// Lucide 0.468.0 path data (ISC); only the icons used by S-022 are vendored.
const LUCIDE={
  grid:[['rect',{width:7,height:7,x:3,y:3}],['rect',{width:7,height:7,x:14,y:3}],['rect',{width:7,height:7,x:14,y:14}],['rect',{width:7,height:7,x:3,y:14}]],
  file:[['path',{d:'M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z'}],['polyline',{points:'14 2 14 8 20 8'}],['line',{x1:8,y1:13,x2:16,y2:13}],['line',{x1:8,y1:17,x2:16,y2:17}]],
  sliders:[['line',{x1:21,y1:4,x2:14,y2:4}],['line',{x1:10,y1:4,x2:3,y2:4}],['line',{x1:21,y1:12,x2:12,y2:12}],['line',{x1:8,y1:12,x2:3,y2:12}],['line',{x1:21,y1:20,x2:16,y2:20}],['line',{x1:12,y1:20,x2:3,y2:20}],['line',{x1:14,y1:2,x2:14,y2:6}],['line',{x1:8,y1:10,x2:8,y2:14}],['line',{x1:16,y1:18,x2:16,y2:22}]],
  search:[['circle',{cx:11,cy:11,r:8}],['path',{d:'m21 21-4.3-4.3'}]],
  checklist:[['path',{d:'m3 17 2 2 4-4'}],['path',{d:'m3 7 2 2 4-4'}],['path',{d:'M13 6h8'}],['path',{d:'M13 12h8'}],['path',{d:'M13 18h8'}]],
  compare:[['circle',{cx:18,cy:18,r:3}],['circle',{cx:6,cy:6,r:3}],['path',{d:'M13 6h3a2 2 0 0 1 2 2v7'}],['path',{d:'M11 18H8a2 2 0 0 1-2-2V9'}]],
  layers:[['path',{d:'m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z'}],['path',{d:'m22 12.5-9.17 4.17a2 2 0 0 1-1.66 0L2 12.5'}],['path',{d:'m22 17.5-9.17 4.17a2 2 0 0 1-1.66 0L2 17.5'}]],
  plug:[['path',{d:'M12 22v-5'}],['path',{d:'M9 8V2'}],['path',{d:'M15 8V2'}],['path',{d:'M18 8v5a6 6 0 0 1-12 0V8Z'}]],
  menu:[['line',{x1:4,y1:6,x2:20,y2:6}],['line',{x1:4,y1:12,x2:20,y2:12}],['line',{x1:4,y1:18,x2:20,y2:18}]],
  close:[['path',{d:'M18 6 6 18'}],['path',{d:'m6 6 12 12'}]],
  upload:[['path',{d:'M12 3v12'}],['path',{d:'m7 8 5-5 5 5'}],['path',{d:'M5 21h14'}]],
  plus:[['path',{d:'M5 12h14'}],['path',{d:'M12 5v14'}]],
  play:[['polygon',{points:'6 3 20 12 6 21 6 3'}]],
  refresh:[['path',{d:'M21 12a9 9 0 1 1-3-6.7'}],['path',{d:'M21 3v6h-6'}]],
  alert:[['circle',{cx:12,cy:12,r:10}],['line',{x1:12,y1:8,x2:12,y2:12}],['line',{x1:12,y1:16,x2:12.01,y2:16}]],
  check:[['path',{d:'m20 6-11 11-5-5'}]],
  clock:[['circle',{cx:12,cy:12,r:10}],['polyline',{points:'12 6 12 12 16 14'}]],
  arrow:[['path',{d:'M5 12h14'}],['path',{d:'m13 6 6 6-6 6'}]],
};
const PRIMARY_DESTINATIONS=[
  {id:'overview',label:'概览',icon:'grid'},
  {id:'documents',label:'文档',icon:'file'},
  {id:'studio',label:'Profile Studio',icon:'sliders'},
  {id:'query',label:'Query Lab',icon:'search'},
  {id:'evaluation-dataset',label:'评估数据集',icon:'checklist'},
  {id:'compare',label:'比较',icon:'compare'},
  {id:'runs',label:'运行记录',icon:'layers'},
  {id:'plugins',label:'插件注册表',icon:'plug'},
];
const ROUTE_META={
  ...Object.fromEntries(PRIMARY_DESTINATIONS.map(item=>[item.id,{label:item.label,parent:item.id}])),
  'evaluation-run':{label:'评估运行',parent:'evaluation-dataset'},
};
const routes=PRIMARY_DESTINATIONS.map(item=>[item.id,item.label]);
const app=document.querySelector('#app');let workspaceId=null,trigger=null,responsiveDesktop=innerWidth>=900,responsiveNavigationFocus=false;
const el=(t,x='',a={})=>{const n=document.createElement(t),problem=x==='COMPARISON_INCOMPATIBLE'&&window.kb2Problem;n.textContent=problem?`${problem.code}${problem.reason?`: ${problem.reason}`:''}`:x;Object.entries(a).forEach(([k,v])=>v!=null&&n.setAttribute(k,String(v)));return n};
const icon=(name,label=null)=>{const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('width','16');svg.setAttribute('height','16');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','2');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');if(label)svg.setAttribute('aria-label',label);else svg.setAttribute('aria-hidden','true');for(const [tag,attrs] of (LUCIDE[name]||LUCIDE.alert)){const node=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,String(value));svg.append(node)}return svg};
const currentRouteId=()=>location.pathname.split('/').filter(Boolean).at(-1)||'overview';
const route=()=>{const meta=ROUTE_META[currentRouteId()]||ROUTE_META.overview;return [meta.parent,meta.label]};
const href=id=>`/workbench/${id}${workspaceId?`?workspace=${workspaceId}`:''}`;
const diagnosisHref=(id,values={})=>{const p=new URLSearchParams(),c=new URL(location).searchParams;if(workspaceId)p.set('workspace',workspaceId);['run','comparison','runType','runState','q'].forEach(k=>{const supplied=Object.prototype.hasOwnProperty.call(values,k)&&values[k]!==undefined,v=supplied?values[k]:c.get(k);if(v&&(((k==='run'||k==='comparison')&&/^[0-9a-f-]{36}$/i.test(v))||(k==='runType'&&/^(INGESTION|QUERY|EVALUATION|COMPARISON|CONTRACT_TEST|UNKNOWN)$/.test(v))||(k==='runState'&&/^(PENDING|RUNNING|SUCCEEDED|FAILED)$/.test(v))||(k==='q'&&v.length<=64)))p.set(k,v)});return `/workbench/${id}${p.size?'?'+p:''}`};
const nativeReplaceState=history.replaceState.bind(history);history.replaceState=(...args)=>{nativeReplaceState(...args);document.querySelectorAll('.nav-link').forEach(link=>{const id=PRIMARY_DESTINATIONS.find(item=>link.pathname.endsWith('/'+item.id))?.id;if(id==='runs'||id==='compare')link.href=diagnosisHref(id)})};
const button=(x,f,disabled=false)=>{const b=el('button',x,{type:'button'});b.disabled=disabled;b.addEventListener('click',f);return b};
async function api(url,options){const r=await fetch(url,options);const j=await r.json();if(!r.ok){window.kb2Problem=j;throw j}return j}

const statusTone=value=>{const key=String(value||'').toLowerCase();if(['ready','available','succeeded','pass'].includes(key))return 'success';if(['running','pending','retrying'].includes(key))return 'info';if(['not_configured','degraded','warn','fallback','skipped'].some(value=>key.includes(value)))return 'warning';return 'failure'};
const statusLabel=value=>({ready:'就绪',available:'可用',succeeded:'成功',running:'运行中',retrying:'重试中',pending:'等待中',not_ready:'未就绪',unavailable:'不可用',not_configured:'未配置',failed:'失败',skipped:'已跳过',skipped_by_condition:'条件跳过',fallback_selected:'已选回退'}[String(value||'').toLowerCase()]||String(value||'未知'));
const statusTag=(label,tone='neutral',attrs={})=>{const tag=el('span','',{class:`status-tag status-${tone}`,...attrs});tag.append(icon(tone==='success'?'check':tone==='info'?'clock':'alert'),el('span',label));return tag};
const iconButton=(name,label,handler)=>{const control=button('',handler);control.className='icon-button';control.setAttribute('aria-label',label);control.setAttribute('title',label);control.append(icon(name));return control};
const commandLink=(label,target,iconName,primary=false)=>{const link=el('a','',{class:`command-link${primary?' command-primary':''}`,href:href(target)});link.append(icon(iconName),el('span',label));return link};
const sectionHeader=(id,title,meta,action=null)=>{const head=el('header','',{class:'section-header'}),copy=el('div','',{class:'section-title'});copy.append(el('h2',title,{id}),el('span',meta,{class:'section-meta'}));head.append(copy);if(action)head.append(action);return head};
const notice=(tone,title,body,actions=[])=>{const box=el('div','',{class:`notice notice-${tone}`,role:tone==='failure'?'alert':'status'}),copy=el('div');box.append(icon(tone==='failure'?'alert':'alert'));copy.append(el('strong',title),el('p',body));if(actions.length){const row=el('div','',{class:'notice-actions'});row.append(...actions);copy.append(row)}box.append(copy);return box};
const emptyState=(title,body,action=null)=>{const box=el('div','',{class:'empty-state'});box.append(el('strong',title),el('p',body));if(action)box.append(action);return box};
const skeletonRows=(count=4)=>{const box=el('div','',{class:'skeleton-rows','aria-label':'正在加载'});for(let index=0;index<count;index++)box.append(el('div','',{class:'skeleton-line'}));return box};
const denseTable=(headers,rows,label)=>{const wrap=el('div','',{class:'table-wrap overview-table-wrap'}),table=el('table','',{class:'dense-table overview-table','aria-label':label}),head=el('thead'),headRow=el('tr');for(const value of headers)headRow.append(el('th',value,{scope:'col'}));head.append(headRow);const body=el('tbody');for(const cells of rows){const row=el('tr');for(const cell of cells){const td=el('td');td.append(cell instanceof Node?cell:document.createTextNode(String(cell)));row.append(td)}body.append(row)}table.append(head,body);wrap.append(table);return wrap};

const overviewSnapshot=(()=>{let snapshot=null,pending=null,loading=false,error=false;const listeners=new Set(),publish=()=>listeners.forEach(listener=>listener({snapshot,loading,error,stale:Boolean(snapshot&&error)}));const load=(force=false)=>{if(pending&&!force)return pending;loading=true;error=false;publish();pending=fetch('/api/workbench/overview').then(response=>{if(!response.ok)throw new Error('OVERVIEW_UNAVAILABLE');return response.json()}).then(value=>{snapshot=value;error=false;return value}).catch(()=>{error=true;return null}).finally(()=>{loading=false;pending=null;publish()});return pending};return {subscribe(listener){listeners.add(listener);listener({snapshot,loading,error,stale:Boolean(snapshot&&error)});return()=>listeners.delete(listener)},load,refresh(){return load(true)}}})();

function nav(){const f=document.createDocumentFragment();for(const item of PRIMARY_DESTINATIONS){const target=item.id==='runs'||item.id==='compare'?diagnosisHref(item.id):href(item.id),a=el('a','',{class:'nav-link',href:target});a.append(icon(item.icon),el('span',item.label));if(item.id==='runs'||item.id==='compare')a.addEventListener('click',()=>a.href=diagnosisHref(item.id));a.addEventListener('click',()=>{if(document.querySelector('#drawer.open'))closeDrawer(false)});if(route()[0]===item.id)a.setAttribute('aria-current','page');f.append(a)}return f}
function closeDrawer(returnFocus=true){const drawer=document.querySelector('#drawer');if(!drawer?.classList.contains('open'))return;drawer.classList.remove('open');drawer.setAttribute('aria-hidden','true');const background=document.querySelector('#workbench-shell');background?.removeAttribute('inert');if(returnFocus)trigger?.focus()}
function syncResponsiveNavigation(){const drawer=document.querySelector('#drawer'),shellRoot=document.querySelector('#workbench-shell'),sidebar=document.querySelector('.sidebar'),menu=document.querySelector('.menu');if(!drawer||!shellRoot||!sidebar||!menu)return;const desktop=innerWidth>=900,transitioned=desktop!==responsiveDesktop,active=document.activeElement,navigationOwned=sidebar.contains(active)||drawer.contains(active)||active===menu||(transitioned&&responsiveNavigationFocus);if(desktop){const wasOpen=drawer.classList.contains('open'),focusWasInDrawer=drawer.contains(active);if(wasOpen)closeDrawer(false);else{drawer.setAttribute('aria-hidden','true');shellRoot.removeAttribute('inert')}if(wasOpen||focusWasInDrawer||(transitioned&&navigationOwned))sidebar.querySelector('.nav-link[aria-current="page"]')?.focus()}else if(sidebar.contains(active)||(transitioned&&navigationOwned))menu.focus();responsiveDesktop=desktop}
function renderContext(host,state){host.replaceChildren();const {snapshot,loading,error,stale}=state;if(!snapshot){for(const label of ['核心','外部能力','Plugin','活动 Run']){const group=el('span','',{class:`context-group ${error?'context-unavailable':'context-loading'}`});group.append(el('span',label,{class:'context-label'}),error?statusTag('状态不可用','failure'):el('span','',{class:'context-skeleton'}));host.append(group)}if(error)host.setAttribute('data-context-state','error');else host.setAttribute('data-context-state','loading');return}const capabilities=snapshot.optionalCapabilities||[],readyCapabilities=capabilities.filter(item=>item.status==='ready').length,plugins=snapshot.plugins||[],runnable=plugins.filter(item=>item.runnable).length;const facts=[
  ['核心',statusLabel(snapshot.coreStatus),statusTone(snapshot.coreStatus),(snapshot.core||[]).map(item=>`${item.id}: ${item.status} (${item.code})`).join('；')],
  ['外部能力',`${readyCapabilities}/${capabilities.length} 就绪`,capabilities.some(item=>item.status==='unavailable')?'failure':capabilities.some(item=>item.status==='not_configured')?'warning':'success',capabilities.map(item=>`${item.id}: ${item.status} (${item.code})`).join('；')||'未声明外部能力'],
  ['Plugin',`${runnable}/${plugins.length} 可运行`,runnable===plugins.length?'success':runnable?'warning':'failure',plugins.map(item=>`${item.pluginId}: ${item.runnable?'runnable':item.reason||'unavailable'}`).join('；')||'未注册 Plugin'],
];for(const [label,value,tone,title] of facts){const group=el('span','',{class:'context-group',title});group.append(el('span',label,{class:'context-label'}),statusTag(value,tone));host.append(group)}const active=el('a','',{class:'context-group context-run',href:diagnosisHref('runs'),'aria-label':`活动 Run ${snapshot.activeRunCount}`});active.append(el('span','活动 Run',{class:'context-label'}),statusTag(String(snapshot.activeRunCount),snapshot.activeRunCount?'info':'neutral'));host.append(active);host.setAttribute('data-context-state',stale?'stale':loading?'refreshing':'ready');if(stale)host.append(el('span','数据可能已过期',{class:'context-stale',role:'status'}))}
function shell(content){app.replaceChildren();const drawer=el('div','',{id:'drawer',class:'drawer',role:'dialog','aria-modal':'true','aria-label':'主导航','aria-hidden':'true'}),drawerPanel=el('div','',{class:'drawer-panel'}),drawerHead=el('div','',{class:'drawer-head'}),drawerNav=el('nav','',{'aria-label':'抽屉主导航'}),close=iconButton('close','关闭导航',()=>closeDrawer());drawerHead.append(el('strong','Knowledge Engine Lite'),close);drawerNav.append(nav());drawerPanel.append(drawerHead,drawerNav);drawer.append(drawerPanel);drawer.addEventListener('click',event=>{if(event.target===drawer)closeDrawer()});app.append(drawer);const shellRoot=el('div','',{class:'shell',id:'workbench-shell'}),side=el('aside','',{class:'sidebar'}),brand=el('div','Knowledge Engine ',{class:'brand'});brand.append(el('span','Lite',{class:'brand-accent'}),el('small','本地工作台'));side.append(brand,el('nav','',{'aria-label':'主导航'}));side.lastChild.append(nav());const body=el('div','',{class:'shell-body'}),top=el('header','',{class:'top'}),crumbs=el('nav','',{'aria-label':'面包屑',class:'crumb'}),crumbList=el('ol'),context=el('div','',{class:'context-bar','aria-live':'polite'}),menu=iconButton('menu','打开导航',()=>{trigger=menu;shellRoot.setAttribute('inert','');drawer.classList.add('open');drawer.removeAttribute('aria-hidden');close.focus()});menu.classList.add('menu');top.append(menu);crumbList.append(el('li','工作台'));crumbList.append(el('li',route()[1],{'aria-current':'page'}));crumbs.append(crumbList);top.append(crumbs,el('span',workspaceId||'本地运行时',{class:'workspace-context'}),context);body.append(top,content);shellRoot.append(side,body);app.append(shellRoot);syncResponsiveNavigation();overviewSnapshot.subscribe(state=>renderContext(context,state));overviewSnapshot.load()}
addEventListener('resize',syncResponsiveNavigation);
document.addEventListener('focusin',event=>{const sidebar=document.querySelector('.sidebar'),drawer=document.querySelector('#drawer'),menu=document.querySelector('.menu');responsiveNavigationFocus=Boolean(sidebar?.contains(event.target)||drawer?.contains(event.target)||event.target===menu)});
document.addEventListener('keydown',e=>{const inspector=document.querySelector('.inspector-drawer.open'),drawer=document.querySelector('#drawer.open'),modal=inspector||drawer;if(e.key==='Escape'){if(inspector){const origin=trigger;if(inspector.classList.contains('registry-detail'))inspector.classList.remove('open');else inspector.remove();origin?.focus()}else if(drawer)closeDrawer();return}if(e.key==='Tab'&&modal){const nodes=[...modal.querySelectorAll('button,a,input,select,textarea,[tabindex]:not([tabindex="-1"])')].filter(node=>!node.disabled),first=nodes[0],last=nodes.at(-1);if(!first)return;if((e.shiftKey&&document.activeElement===first)||(!e.shiftKey&&document.activeElement===last)){e.preventDefault();(e.shiftKey?last:first).focus()}}});
function heading(name,sub){const h=el('div','',{class:'title-row'}),copy=el('div');copy.append(el('h1',name),el('small',sub));h.append(copy);return h}
function report(result,host){host.querySelector('.diagnostics')?.remove();const d=el('div','',{class:'diagnostics','aria-live':'polite'});if(result.valid)d.append(el('span',result.planDigest?`已编译: ${result.planDigest}`:'配置有效',{class:'ready'}));else result.diagnostics.forEach(x=>{const b=button(`${x.location}: ${x.code}`,()=>host.querySelector('textarea,select,input')?.focus());b.className='error';b.dataset.location=x.location;d.append(b)});host.append(d)}

const formatTime=value=>value?new Intl.DateTimeFormat('zh-CN',{timeZone:'UTC',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)):'-';
const formatDuration=run=>{if(!run.startedAt||!run.endedAt)return '-';const elapsed=Math.max(0,new Date(run.endedAt)-new Date(run.startedAt));return elapsed<1000?`${elapsed} ms`:elapsed<60000?`${(elapsed/1000).toFixed(1)} s`:`${Math.floor(elapsed/60000)}m ${Math.floor((elapsed%60000)/1000)}s`};
const shortIdentity=(value,length=8)=>{const code=el('code',String(value).slice(0,length),{title:String(value)});code.append(el('span',String(value),{class:'sr-only'}));return code};
function overviewHeader(){const row=heading('概览','运行时状态与最近的实验活动'),commands=el('nav','',{'aria-label':'概览主命令',class:'overview-commands'});commands.append(commandLink('提交文档','documents','upload',true),commandLink('新建 Profile','studio','plus'),commandLink('打开 Query Lab','query','search'),commandLink('运行评估','evaluation-dataset','play'));row.classList.add('overview-title');row.append(commands);return row}
function loadingOverview(host){const dependency=el('section','',{class:'dependency-band','aria-labelledby':'dependency-title'});dependency.append(sectionHeader('dependency-title','依赖状态','正在检查'),skeletonRows(2));const split=el('div','',{class:'overview-grid'}),runs=el('section','',{class:'overview-runs','aria-labelledby':'recent-runs-title'}),side=el('aside','',{class:'overview-side'});runs.append(sectionHeader('recent-runs-title','最近运行','正在加载'),skeletonRows(6));const failures=el('section','',{class:'overview-failures','aria-labelledby':'failed-runs-title'}),comparisons=el('section','',{class:'overview-comparisons','aria-labelledby':'comparisons-title'});failures.append(sectionHeader('failed-runs-title','失败分诊','正在加载'),skeletonRows(2));comparisons.append(sectionHeader('comparisons-title','最近比较','正在加载'),skeletonRows(2));side.append(failures,comparisons);split.append(runs,side);host.replaceChildren(dependency,split)}
function unavailableOverview(host,loading){const retry=()=>button('重新刷新',()=>overviewSnapshot.refresh(),loading),dependency=el('section','',{class:'dependency-band overview-unavailable','aria-labelledby':'dependency-title'});dependency.append(sectionHeader('dependency-title','依赖状态','不可用'),emptyState('依赖状态不可用','重新刷新以读取核心、外部能力与 Plugin 状态。',retry()));const split=el('div','',{class:'overview-grid'}),runs=el('section','',{class:'overview-runs overview-unavailable','aria-labelledby':'recent-runs-title'}),side=el('aside','',{class:'overview-side'}),failures=el('section','',{class:'overview-failures overview-unavailable','aria-labelledby':'failed-runs-title'}),comparisons=el('section','',{class:'overview-comparisons overview-unavailable','aria-labelledby':'comparisons-title'});runs.append(sectionHeader('recent-runs-title','最近运行','不可用'),emptyState('最近运行不可用','重新刷新以读取最近运行记录。',retry()));failures.append(sectionHeader('failed-runs-title','失败分诊','不可用'),emptyState('失败分诊不可用','重新刷新以读取待分诊失败。',retry()));comparisons.append(sectionHeader('comparisons-title','最近比较','不可用'),emptyState('最近比较不可用','重新刷新以读取比较结果。',retry()));side.append(failures,comparisons);split.append(runs,side);host.replaceChildren(notice('failure','无法刷新概览','运行时概览暂时不可用。主命令仍可使用。',[retry()]),dependency,split)}
function overviewSnapshotView(host,snapshot,{loading,error,stale}){const parts=[];if(stale)parts.push(notice('failure','概览刷新失败','保留上一次成功快照，数据可能已过期。',[button('重新刷新',()=>overviewSnapshot.refresh(),loading)]));const dependencies=el('section','',{class:'dependency-band','aria-labelledby':'dependency-title'}),items=el('div','',{class:'dependency-items'}),refresh=iconButton('refresh','刷新概览',()=>overviewSnapshot.refresh());refresh.disabled=loading;dependencies.append(sectionHeader('dependency-title','依赖状态',`检查于 ${formatTime(snapshot.checkedAt)}`,refresh));for(const item of snapshot.core||[]){const cell=el('div','',{class:'dependency-item'});cell.append(el('span',item.id,{class:'mono'}),statusTag(statusLabel(item.status),statusTone(item.status)),el('span',item.code,{class:'safe-code'}));items.append(cell)}for(const item of snapshot.optionalCapabilities||[]){const cell=el('div','',{class:'dependency-item'});cell.append(el('span',item.id,{class:'mono'}),statusTag(statusLabel(item.status),statusTone(item.status)),el('span',item.code,{class:'safe-code'}));items.append(cell)}for(const item of snapshot.plugins||[]){const cell=el('div','',{class:'dependency-item'});cell.append(el('span',item.pluginId,{class:'mono'}),statusTag(item.runnable?'可运行':'不可运行',item.runnable?'success':'failure'),el('span',item.reason||'OK',{class:'safe-code'}));items.append(cell)}dependencies.append(items);const unavailable=(snapshot.coreStatus!=='ready')||(snapshot.core||[]).some(item=>item.status!=='ready')||(snapshot.optionalCapabilities||[]).some(item=>item.status==='unavailable')||(snapshot.plugins||[]).some(item=>!item.runnable);if(unavailable)dependencies.append(notice('warning','部分依赖不可用','核心、外部能力与 Plugin 状态彼此独立；请按安全代码检查对应依赖。',[button('重新检查',()=>overviewSnapshot.refresh(),loading),commandLink('打开插件注册表','plugins','plug')]));parts.push(dependencies);
  const split=el('div','',{class:'overview-grid'}),runsSection=el('section','',{class:'overview-runs','aria-labelledby':'recent-runs-title'}),viewAll=el('a','查看全部',{class:'section-action',href:diagnosisHref('runs')});runsSection.append(sectionHeader('recent-runs-title','最近运行',`${(snapshot.recentRuns||[]).length} 条`,viewAll));if((snapshot.recentRuns||[]).length){const rows=snapshot.recentRuns.map(run=>{const inspect=el('a','检查',{class:'table-action',href:diagnosisHref('runs',{run:run.id,runType:String(run.engineKind).toUpperCase()})});return [shortIdentity(run.id),run.engineKind,shortIdentity(run.planDigest,12),statusTag(statusLabel(run.state),statusTone(run.state)),formatDuration(run),formatTime(run.createdAt),inspect]});runsSection.append(denseTable(['Run','引擎','计划摘要','状态','耗时','创建时间','操作'],rows,'最近运行'))}else runsSection.append(emptyState('尚无运行记录','提交文档后，运行记录会出现在这里。',commandLink('提交文档','documents','upload',true)));
  const side=el('aside','',{class:'overview-side'}),failures=el('section','',{class:'overview-failures','aria-labelledby':'failed-runs-title'}),failed=(snapshot.recentRuns||[]).filter(run=>run.failure);failures.append(sectionHeader('failed-runs-title','失败分诊',`${failed.length} 条`));if(failed.length){for(const run of failed){const row=el('div','',{class:'triage-row'}),identity=el('div','',{class:'triage-identity'}),actions=el('div','',{class:'row-actions'}),runValues={run:run.id,runType:String(run.engineKind).toUpperCase()};identity.append(shortIdentity(run.id),el('span',run.engineKind,{class:'section-meta'}));actions.append(el('a','检查',{class:'text-action',href:diagnosisHref('runs',runValues)}));if(run.failure.retryable)actions.append(el('a','恢复指引',{class:'text-action recovery-action',href:diagnosisHref('runs',runValues)}));row.append(identity,el('code',run.failure.code,{class:'failure-code'}),actions);failures.append(row)}}else failures.append(emptyState('没有待分诊失败','最近运行中没有安全失败记录。'));
  const comparisons=el('section','',{class:'overview-comparisons','aria-labelledby':'comparisons-title'}),recent=snapshot.recentComparisons||[];comparisons.append(sectionHeader('comparisons-title','最近比较',`${recent.length} 条`,el('a','打开比较',{class:'section-action',href:diagnosisHref('compare')})));if(recent.length){for(const item of recent){const row=el('a','',{class:'comparison-row',href:diagnosisHref('compare'),title:`Artifact ${item.artifactId}`}),top=el('span','',{class:'comparison-summary'});top.append(el('strong',item.mode),item.axis?el('span',item.axis,{class:'status-tag status-info'}):el('span','多轴',{class:'status-tag status-neutral'}));row.append(top,el('code',item.recommendation),el('time',formatTime(item.createdAt),{datetime:item.createdAt}));comparisons.append(row)}}else comparisons.append(emptyState('尚无比较结果','完成评估比较后，摘要会出现在这里。'));side.append(failures,comparisons);split.append(runsSection,side);parts.push(split);host.replaceChildren(...parts)}
function overview(){const main=el('main','',{class:'overview-page','data-overview-state':'loading'}),surface=el('div','',{class:'overview-surface','aria-live':'polite'});main.append(overviewHeader(),surface);loadingOverview(surface);shell(main);overviewSnapshot.subscribe(state=>{const stateName=state.snapshot?(state.stale?'stale':state.loading?'refreshing':'populated'):state.error?'error':'loading';main.dataset.overviewState=stateName;if(!state.snapshot){if(state.error)unavailableOverview(surface,state.loading);else loadingOverview(surface);return}overviewSnapshotView(surface,state.snapshot,state)});overviewSnapshot.load()}
function studio(){const main=el('main'),kind=el('select','',{'aria-label':'Profile 类型'});[['ingestion','Ingestion'],['query','Query']].forEach(([v,n])=>kind.append(el('option',n,{value:v})));const search=el('input','',{placeholder:'搜索工作配置','aria-label':'搜索工作配置'}),list=el('aside','',{class:'studio-list','aria-label':'已保存 Profile'}),editor=el('section','',{class:'studio-editor'}),layout=el('div','',{class:'studio-layout'});let current=null,valid=false,compiled=false,mode='form',yamlSource='',lastResult=null;const details=new Map();
 const payload=()=>mode==='yaml'?{kind:current.kind,source:yamlSource,mediaType:'application/yaml'}:{kind:current.kind,document:current.document};
 const dirty=()=>{valid=false;compiled=false};
 const candidates=async record=>{const result=await api('/api/workbench/plugins/compatible',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({kind:current.kind,document:current.document,stageId:record.stageId})}).catch(()=>[]);return Array.isArray(result)?result:[]};
 const descriptor=async pluginId=>{if(!details.has(pluginId))details.set(pluginId,api(`/api/workbench/plugins/${encodeURIComponent(pluginId)}`).catch(()=>null));return details.get(pluginId)};
 const records=()=>{const profile=current.document.profiles?.[0]||{};if(current.kind==='query')return (profile.stages||[]).map((stage,index)=>({stage,index,label:stage.stage_id,stageId:stage.stage_id}));const output=[];Object.entries(profile.axes||{}).forEach(([axis,axisValue])=>{const subStages=axisValue.sub_stages||[{stage_id:axis,candidates:axisValue.candidates||[],on_exhausted:axisValue.on_exhausted}];subStages.forEach(sub=>sub.candidates?.forEach((candidate,index)=>output.push({stage:candidate,candidate,index,label:`${axis}.${sub.stage_id} / ${index?'回退 '+(index+1):'首选'}`,stageId:`${axis}.${sub.stage_id}`,subStage:sub})));});return output};
 const conditionControl=(stage,label)=>{const choice=el('select','',{'aria-label':`${label} 条件`});choice.append(el('option','始终执行',{value:'always'}),el('option','仅 PDF 文档',{value:'pdf'}));choice.value=stage.when?.eq?.[0]==='document.extension'&&stage.when.eq[1]==='pdf'?'pdf':'always';choice.addEventListener('change',()=>{if(choice.value==='pdf')stage.when={eq:['document.extension','pdf']};else delete stage.when;dirty()});return choice};
 const policyControls=(stage,record)=>{const policy=el('div','',{class:'editor-actions'});policy.append(conditionControl(stage,record.label));if(current.kind==='query'){const attempts=el('input','',{type:'number',min:1,max:3,'aria-label':`${record.label} 最大尝试次数`});attempts.value=stage.max_attempts||1;attempts.addEventListener('input',()=>{const value=Number(attempts.value);if(value>=1&&value<=3)stage.max_attempts=value;dirty()});policy.append(attempts)}else{const quality=stage.accept_quality||[];['PASS','WARN','FAIL'].forEach(value=>{const enabled=el('input','',{type:'checkbox','aria-label':`${record.label} 接受 ${value}`});enabled.checked=quality.includes(value);enabled.addEventListener('change',()=>{stage.accept_quality=['PASS','WARN','FAIL'].filter(item=>item===value?enabled.checked:(stage.accept_quality||[]).includes(item));dirty()});policy.append(enabled,el('span',value));});if(record.subStage)policy.append(el('span',record.index?'回退候选':'首选候选',{class:'muted'}));}return policy};
 const schemaFields=(stage,schema,label)=>{const box=el('div','',{class:'stage-list','aria-label':`${label} 参数`}),properties=schema&&schema.type==='object'&&schema.properties&&typeof schema.properties==='object'?schema.properties:null;if(!properties){box.append(el('pre',JSON.stringify(schema||{},null,2),{class:'schema'}));return box}Object.entries(properties).forEach(([key,field])=>{if(!field||typeof field!=='object')return;const currentValue=stage.configuration?.[key]??field.default;const row=el('div','',{class:'stage-row'}),name=el('label',key);let input=null;if(Array.isArray(field.enum)){input=el('select','',{'aria-label':`${label} ${key}`});field.enum.forEach(value=>input.append(el('option',String(value),{value:String(value)})));input.value=String(currentValue??field.enum[0])}else if(['string','integer','number','boolean'].includes(field.type)){if(field.type==='boolean'){input=el('input','',{type:'checkbox','aria-label':`${label} ${key}`});input.checked=Boolean(currentValue)}else{input=el('input','',{type:field.type==='string'?'text':'number','aria-label':`${label} ${key}`,min:field.minimum,max:field.maximum,step:field.type==='integer'?1:'any'});input.value=currentValue??''}}else if(field.type==='object'&&field.properties&&Object.values(field.properties).every(x=>x&&typeof x==='object'&&['string','integer','number','boolean'].includes(x.type))){input=el('input','',{type:'text','aria-label':`${label} ${key} 对象`});input.value=JSON.stringify(currentValue??field.default??{});input.addEventListener('change',()=>{try{const value=JSON.parse(input.value);if(value&&typeof value==='object'&&!Array.isArray(value))stage.configuration[key]=value;else input.value=JSON.stringify(stage.configuration?.[key]??{});dirty()}catch{input.value=JSON.stringify(stage.configuration?.[key]??{})}});row.append(name,input);box.append(row);return}else{row.append(name,el('span','只读 Schema',{class:'muted'}),el('pre',JSON.stringify(field,null,2),{class:'schema'}));box.append(row);return}input.addEventListener('input',()=>{stage.configuration??={};stage.configuration[key]=field.type==='boolean'?input.checked:field.type==='integer'?Number(input.value):field.type==='number'?Number(input.value):input.value;dirty()});row.append(name,input);box.append(row)});return box};
 const renderRecord=async(record,box)=>{const stage=record.stage,row=el('div','',{class:'stage-row'}),choice=el('select','',{'aria-label':`${record.label} 插件`});choice.append(el('option','加载兼容插件…',{value:''}));row.append(el('strong',record.label),choice);if(current.kind==='query')row.append(button('上移',()=>move(record.index,-1),record.index===0),button('下移',()=>move(record.index,1),record.index===records().length-1));box.append(row);const options=await candidates(record);choice.replaceChildren();if(!options.some(item=>item.pluginId===stage.plugin_id))choice.append(el('option',`${stage.plugin_id}（当前不可兼容）`,{value:stage.plugin_id,disabled:'true'}));options.forEach(item=>choice.append(el('option',item.pluginId,{value:item.pluginId})));choice.value=stage.plugin_id;choice.addEventListener('change',async()=>{stage.plugin_id=choice.value;stage.configuration={};dirty();render()});const info=await descriptor(stage.plugin_id);box.append(policyControls(stage,record),schemaFields(stage,info?.configurationSchema,record.label));};
 const render=()=>{editor.replaceChildren();if(!current){editor.append(el('div','没有保存的工作配置。',{class:'empty'}));return}const bar=el('div','',{class:'editor-heading'});bar.append(el('h2',current.profileId),button('表单',()=>{if(mode==='yaml'&&yamlSource!==JSON.stringify(current.document,null,2)){lastResult={valid:false,diagnostics:[{code:'YAML_VALIDATE_REQUIRED',location:'/'}]};render();report(lastResult,editor);return}mode='form';render()}),button('YAML',()=>{mode='yaml';render()}));editor.append(bar);if(mode==='yaml'){const source=el('textarea','',{class:'profile-source','aria-label':'YAML Profile'});source.value=yamlSource||JSON.stringify(current.document,null,2);source.addEventListener('input',()=>{yamlSource=source.value;dirty()});editor.append(source)}else{const box=el('div','',{class:'stage-list','aria-label':'有序阶段'});records().forEach(record=>{renderRecord(record,box)});editor.append(box)}const actions=el('div','',{class:'editor-actions'}),reason=compiled&&current.saved?'':'需先保存并成功编译';actions.append(button('验证',()=>request('validate')),button('编译预览',()=>request('compile')),button('保存',()=>save(),!valid),button('复制候选',()=>copy()),button('干运行',()=>dry(),!(compiled&&current.saved)));if(reason)actions.append(el('span',reason,{class:'muted'}));editor.append(actions)};
 const move=(i,d)=>{const xs=current.document.profiles[0].stages,j=i+d;[xs[i],xs[j]]=[xs[j],xs[i]];valid=false;compiled=false;render()};
 const request=async action=>{const r=await api(`/api/workbench/profiles/${action}`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload())});lastResult=r;valid=r.valid;compiled=action==='compile'&&r.valid;if(r.normalizedDocument){current.document=r.normalizedDocument;yamlSource=JSON.stringify(r.normalizedDocument,null,2)}render();report(lastResult,editor)};
 const save=async()=>{if(!valid)return;const r=await api(`/api/workbench/profiles/${current.profileId}`,{method:'PUT',headers:{'content-type':'application/json'},body:JSON.stringify(payload())});current=r;current.saved=true;await refresh()};
 const copy=async()=>{const copyId=prompt('候选 Profile ID');if(!copyId)return;const x=await api(`/api/workbench/profiles/${current.profileId}/copy?copy_id=${encodeURIComponent(copyId)}`,{method:'POST'});current=x;current.saved=true;valid=true;compiled=false;await refresh()};
const dry=async()=>{const questionArtifactId=prompt('Question Artifact UUID'),artifactId=prompt('Search Artifact UUID'),contentDigest=prompt('Search Artifact digest (64 hex)'),byteSize=prompt('Search Artifact byte size');if(!questionArtifactId||!artifactId||!contentDigest||byteSize===null)return;await api(`/api/workbench/profiles/${current.profileId}/dry-run`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({kind:'query',questionArtifactId,searchArtifact:{artifact_id:artifactId,artifact_type:'search.index.result',schema_revision:'v1',content_digest:contentDigest,byte_size:Number(byteSize)}})})};
 const refresh=async()=>{const rows=await api(`/api/workbench/profiles?kind=${kind.value}&q=${encodeURIComponent(search.value)}`);list.replaceChildren(kind,search);rows.forEach(x=>list.append(button(x.profileId,async()=>{current=await api(`/api/workbench/profiles/${x.profileId}`);current.saved=true;valid=true;compiled=false;yamlSource=JSON.stringify(current.document,null,2);render()})));render()};kind.addEventListener('change',refresh);search.addEventListener('input',refresh);main.append(heading('Profile Studio','声明式工作配置'),layout);layout.append(list,editor);shell(main);refresh()}
function plugins(){const main=el('main'),tools=el('div','',{class:'registry-tools'}),query=el('input','',{placeholder:'搜索插件','aria-label':'搜索插件'}),kind=el('input','',{placeholder:'类型','aria-label':'插件类型'}),runner=el('select','',{'aria-label':'Runner'}),readiness=el('select','',{'aria-label':'运行状态'});runner.append(el('option','全部 Runner',{value:''}),el('option','in_process',{value:'in_process'}),el('option','container',{value:'container'}));readiness.append(el('option','全部',{value:''}),el('option','可运行',{value:'available'}),el('option','不可运行',{value:'unavailable'}));tools.append(query,kind,runner,readiness);const list=el('section','',{class:'registry-list','aria-label':'插件注册表','aria-live':'polite'}),detail=el('aside','',{class:'registry-detail','aria-label':'插件契约详情'}),layout=el('div','',{class:'registry-layout'});let refreshVersion=0;detail.append(emptyState('未选择 Plugin','从注册表中选择一个 Plugin 查看契约。'));const openDetail=()=>{detail.scrollTop=0;if(innerWidth<900){detail.classList.add('inspector-drawer','open');detail.setAttribute('role','dialog');detail.setAttribute('aria-modal','true');detail.tabIndex=-1;detail.style.display='block';detail.focus()}};const inspect=async(id,origin)=>{trigger=origin;detail.replaceChildren(skeletonRows(5));openDetail();try{const x=await api(`/api/workbench/plugins/${encodeURIComponent(id)}`),close=button('关闭',()=>{detail.classList.remove('open');trigger?.focus()});detail.replaceChildren(close,el('h2',x.pluginId),statusTag(x.runnable?'可运行':`不可运行: ${x.reason||'DEPENDENCY_UNAVAILABLE'}`,x.runnable?'success':'failure'),el('h3','输入端口'),el('pre',JSON.stringify(x.inputPorts,null,2),{class:'schema'}),el('h3','输出端口'),el('pre',JSON.stringify(x.outputPorts,null,2),{class:'schema'}),el('h3','能力、资源与超时'),el('pre',JSON.stringify({capabilities:x.capabilities,resourceHints:x.resourceHints,timeoutSeconds:x.timeoutSeconds,contractTests:x.contractTests,recentRuns:x.recentRuns},null,2),{class:'schema'}),el('h3','配置 Schema'),el('pre',JSON.stringify(x.configurationSchema,null,2),{class:'schema'}),el('h3','安全示例'),el('pre',JSON.stringify(x.safeExample,null,2),{class:'schema'}));openDetail()}catch{detail.replaceChildren(notice('failure','Plugin 契约不可用','PLUGIN_DETAIL_UNAVAILABLE',[button('重试',()=>inspect(id,origin))]));openDetail()}};const refresh=async()=>{const request=++refreshVersion,params=new URLSearchParams();if(kind.value)params.set('kind',kind.value);if(runner.value)params.set('runner',runner.value);if(readiness.value)params.set('readiness',readiness.value);if(query.value)params.set('q',query.value);list.replaceChildren(skeletonRows(6));try{const xs=await api(`/api/workbench/plugins${params.size?'?'+params:''}`);if(request!==refreshVersion)return;if(!xs.length){list.replaceChildren(emptyState('没有匹配的 Plugin','调整搜索或筛选条件。'));return}const rows=xs.map(x=>{const activate=button(x.pluginId,event=>inspect(x.pluginId,event.currentTarget));activate.className='registry-select';return [activate,x.kind,x.runner,statusTag(x.runnable?'可运行':'不可运行',x.runnable?'success':'failure')]});list.replaceChildren(el('div',`${xs.length} 个已注册 Plugin`,{class:'registry-summary'}),denseTable(['Plugin ID','类型','Runner','本地状态'],rows,'Plugin Registry'))}catch{if(request===refreshVersion)list.replaceChildren(notice('failure','Plugin Registry 不可用','PLUGIN_REGISTRY_UNAVAILABLE',[button('重试',refresh)]))}};[query,kind,runner,readiness].forEach(x=>x.addEventListener(x.tagName==='INPUT'?'input':'change',refresh));main.append(heading('插件注册表','只读 Registry 契约与运行状态'),tools,layout);layout.append(list,detail);shell(main);refresh()}
const displayValue=value=>value===undefined||value===null||value===''?'不可用':typeof value==='object'?JSON.stringify(value):String(value);
const signalValue=value=>value===undefined||value===null||(Array.isArray(value)&&value.length===0)||(typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===0)?'不可用':value;
const definitionRows=(entries,className='definition-grid')=>{const list=el('dl','',{class:className});for(const [label,value] of entries){list.append(el('dt',label),el('dd',displayValue(value),typeof value==='string'&&value.length>28?{class:'mono'}:{}))}return list};
const modalKeys=(surface,dismiss,event)=>{if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();dismiss();return}if(event.key!=='Tab')return;const nodes=[...surface.querySelectorAll('button,input,select,textarea,[tabindex]:not([tabindex="-1"])')].filter(node=>!node.disabled),first=nodes[0],last=nodes.at(-1);if(!first)return;if((event.shiftKey&&document.activeElement===first)||(!event.shiftKey&&document.activeElement===last)){event.preventDefault();(event.shiftKey?last:first).focus()}};
const setModalScrollLock=locked=>{document.documentElement.classList.toggle('modal-open',locked);document.body.classList.toggle('modal-open',locked)};
function createDialogShell(label,origin){const backdrop=el('div','',{class:'modal-backdrop'}),dialog=el('section','',{class:'upload-dialog',role:'dialog','aria-modal':'true','aria-label':label,tabindex:'-1'}),background=document.querySelector('#workbench-shell');let closed=false;const dismiss=()=>{if(closed)return;closed=true;document.removeEventListener('keydown',onKey,true);backdrop.remove();background?.removeAttribute('inert');setModalScrollLock(false);origin?.focus()},onKey=event=>modalKeys(dialog,dismiss,event);backdrop.addEventListener('click',event=>{if(event.target===backdrop)dismiss()});document.addEventListener('keydown',onKey,true);background?.setAttribute('inert','');setModalScrollLock(true);backdrop.append(dialog);document.body.append(backdrop);return {dialog,dismiss,focus(){dialog.focus()}}}
const locatorLabel=locator=>{if(!locator||!Object.keys(locator).length)return '定位不可用';const parts=[locator.kind,locator.page_number!=null?`第 ${locator.page_number} 页`:null,locator.sheet_name?`工作表 ${locator.sheet_name}`:null,locator.slide_number!=null?`第 ${locator.slide_number} 张`:null,locator.section?`章节 ${locator.section}`:null,locator.cell_range||locator.range].filter(Boolean);return parts.join(' / ')||JSON.stringify(locator)};
const tabLabel=tab=>({raw:'原始文本',canonical:'Canonical',tree:'结构树',table:'表格',chunks:'Chunks',metadata:'元数据',lineage:'Lineage'}[tab]||tab);
function inspector(id, returnFocus, selectedLocator) {
  trigger = returnFocus;
  const overlay = el("div", "", { class: "artifact-overlay" }),
    scrim = el("div", "", { class: "artifact-scrim" }),
    drawer = el("aside", "", {
      class: "artifact-inspector inspector-drawer open",
      role: "dialog",
      "aria-modal": "true",
      "aria-label": "Artifact 检查器",
      tabindex: "-1",
    }),
    background = document.querySelector("#workbench-shell");
  let closed = false;
  const dismiss = () => {
      if (closed) return;
      closed = true;
      document.removeEventListener("keydown", onKey, true);
      overlay.remove();
      background?.removeAttribute("inert");
      setModalScrollLock(false);
      returnFocus?.focus();
    },
    onKey = (event) => modalKeys(drawer, dismiss, event),
    close = iconButton("close", "关闭 Artifact 检查器", dismiss),
    loadingHeader = el("header", "", { class: "artifact-header" });
  loadingHeader.append(el("h2", "Artifact 检查器"), close);
  document.addEventListener("keydown", onKey, true);
  background?.setAttribute("inert", "");
  setModalScrollLock(true);
  scrim.addEventListener("click", dismiss);
  overlay.append(scrim, drawer);
  document.body.append(overlay);
  drawer.append(
    loadingHeader,
    el("p", "加载 Artifact…", {
      class: "artifact-loading",
      "aria-live": "polite",
    }),
  );
  api(`/api/workbench/artifacts/${id}`)
    .then((x) => {
      const view = x.view || {},
        tabs = el("div", "", {
          class: "inspector-tabs",
          role: "tablist",
          "aria-label": "Artifact 视图",
        }),
        body = el("section", "", {
          class: "inspector-body",
          role: "tabpanel",
          tabindex: "0",
        }),
        header = el("header", "", { class: "artifact-header" }),
        identity = el("div");
      identity.append(
        el("span", "ARTIFACT", { class: "eyebrow" }),
        el("h2", `${x.artifactType} / ${x.schemaRevision}`),
        el("code", id, { class: "artifact-identity" }),
        statusTag(
          view.available === false ? "Schema 不可用" : "Schema 可用",
          view.available === false ? "failure" : "success",
        ),
      );
      header.append(identity, close);
      let active = null;
      const selectPair = (key) => {
          drawer
            .querySelectorAll("[data-stable-id]")
            .forEach((node) =>
              node.classList.toggle(
                "source-selected",
                node.dataset.stableId===key,
              ),
            );
          const selected = [
              ...drawer.querySelectorAll("[data-stable-id]"),
            ].find((node) => node.dataset.stableId === key),
            identity = selected?.dataset.selectionLabel;
          summary.textContent = selected
            ? `已选择来源：${identity ? `${identity} / ` : ""}${locatorLabel(JSON.parse(selected.dataset.locator || "{}"))}`
            : "未选择来源";
        },
        summary = el("p", "未选择来源", {
          class: "locator-summary",
          "aria-live": "polite",
        });
      const pairedView = (rows, tab) => {
        if (!rows?.length)
          return emptyState(
            `${tabLabel(tab)} 不可用`,
            "该 Artifact Schema 未返回此视图。",
          );
        const split = el("div", "", { class: "artifact-source-grid" }),
          list = el("section", "", {
            class: "inspector-list",
            "aria-label": "稳定对象列表",
          }),
          source = el("section", "", {
            class: "source-view",
            "aria-label": "源定位",
          });
        rows.forEach((row) => {
          const bindings =
            tab === "chunks"
              ? (row.citations||[]).map((citation, index) => ({
                  locator: citation.locator,
                  suffix: ` / citation ${index + 1}`,
                  elementId: citation.elementId,
                }))
              : [{ locator: row.locator, suffix: "" }];
          for (const binding of bindings) {
            const locator = binding.locator || {},
              stable = `${row.id}|${JSON.stringify(locator)}`,
              item = button("", () => selectPair(stable)),
              origin = button("", () => selectPair(stable));
            item.className = "artifact-object";
            item.append(
              el("strong", row.id || "未命名对象", { class: "mono" }),
              el("span", `${row.text || "内容不可用"}${binding.suffix}`),
              tab === "chunks"
                ? el(
                    "small",
                    `Source elements: ${(row.sourceElementIds || []).join(", ") || "不可用"}`,
                  )
                : el("span", ""),
            );
            origin.className = "locator-entry";
            origin.append(
              el("strong", locatorLabel(locator)),
              el("code", JSON.stringify(locator)),
            );
            for (const node of [item, origin]) {
              node.dataset.stableId = stable;
              node.dataset.locator = JSON.stringify(locator);
            }
            list.append(item);
            source.append(origin);
          }
        });
        split.append(list, source);
        return split;
      };
      const tableView = () => {
        const rows = view.tables || [];
        if (!rows.length)
          return emptyState(
            "表格不可用",
            "该 Artifact Schema 未返回表格结构。",
          );
        const split = el("div", "", { class: "artifact-source-grid" }),
          host = el("section", "", {
            class: "artifact-tables inspector-list",
            "aria-label": "表格对象列表",
          }),
          source = el("section", "", {
            class: "source-view",
            "aria-label": "表格源定位",
          });
        for (const table of rows) {
          const section = el("section", "", { class: "artifact-table" }),
            stable = `${table.id}|${JSON.stringify(table.locator || {})}`,
            open = button(`${table.id} / ${locatorLabel(table.locator)}`, () =>
              selectPair(stable),
            ),
            origin = button("", () => selectPair(stable)),
            wrap = el("div", "", { class: "table-wrap" }),
            grid = el("table", "", { class: "dense-table" }),
            head = el("tr");
          ["行", "列", "内容", "行跨度", "列跨度"].forEach((value) =>
            head.append(el("th", value, { scope: "col" })),
          );
          grid.append(head);
          for (const cell of table.cells || []) {
            const row = el("tr");
            [
              cell.row_index ?? cell.row,
              cell.column_index ?? cell.column,
              cell.text ?? cell.value,
              cell.row_span ?? 1,
              cell.column_span ?? 1,
            ].forEach((value) => row.append(el("td", displayValue(value))));
            grid.append(row);
          }
          wrap.append(grid);
          origin.className = "locator-entry";
          origin.append(
            el("strong", locatorLabel(table.locator)),
            el("code", JSON.stringify(table.locator || {})),
          );
          for (const node of [open, origin]) {
            node.dataset.stableId = stable;
            node.dataset.locator = JSON.stringify(table.locator || {});
            node.dataset.selectionLabel = table.id || "未命名表格";
          }
          section.append(open, wrap);
          host.append(section);
          source.append(origin);
        }
        split.append(host, source);
        return split;
      };
      const render = (tab) => {
        active = tab;
        [...tabs.children].forEach((control) => {
          const selected = control.dataset.tab === tab;
          control.setAttribute("aria-selected", String(selected));
          control.tabIndex = selected ? 0 : -1;
        });
        body.setAttribute("aria-labelledby", `artifact-tab-${tab}`);
        body.replaceChildren();
        summary.textContent = "未选择来源";
        if (tab === "raw")
          body.append(
            view.rawText
              ? el("pre", view.rawText, { class: "raw-preview" })
              : emptyState(
                  "原始文本不可用",
                  view.reason || "该 Artifact 未提供可安全展示的原始文本。",
                ),
          );
        else if (tab === "canonical" || tab === "tree" || tab === "chunks")
          body.append(
            pairedView(tab === "chunks" ? view.chunks : view.elements, tab),
            summary,
          );
        else if (tab === "table") body.append(tableView(), summary);
        else if (tab === "metadata")
          body.append(
            definitionRows(
              [
                ["Artifact 类型", x.artifactType],
                ["Schema", x.schemaRevision],
                ["摘要", x.summary],
                ["指标", signalValue(x.metrics)],
                ["质量", signalValue(x.quality)],
              ],
              "definition-grid metadata-grid",
            ),
          );
        else if (tab === "lineage") {
          const lineage = el("ol", "", { class: "lineage-list" }),
            producer = x.producer || {};
          lineage.append(
            el("li", `生产者 Run ID：${producer.runId || "不可用"}`),
            el("li", `生产者 Plugin ID：${producer.pluginId || "不可用"}`),
            el("li", `当前 Artifact：${id}`),
          );
          for (const parent of x.parents || [])
            lineage.append(el("li", `父 Artifact：${parent}`));
          body.append(lineage);
        }
      };
      for (const tab of view.tabs || []) {
        const control = button(tabLabel(tab), () => render(tab));
        control.dataset.tab = tab;
        control.id = `artifact-tab-${tab}`;
        control.setAttribute("role", "tab");
        control.setAttribute("aria-controls", "artifact-tabpanel");
        tabs.append(control);
      }
      body.id = "artifact-tabpanel";
      tabs.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
          return;
        event.preventDefault();
        const controls = [...tabs.querySelectorAll("[role=tab]")],
          index = controls.findIndex(
            (control) => control.dataset.tab === active,
          ),
          next =
            event.key === "Home"
              ? 0
              : event.key === "End"
                ? controls.length - 1
                : (index +
                    (event.key === "ArrowLeft" ? -1 : 1) +
                    controls.length) %
                  controls.length;
        controls[next].focus();
        render(controls[next].dataset.tab);
      });
      drawer.replaceChildren(header, tabs, body);
      render((view.tabs || [])[0]);
      if (selectedLocator) {
        const encoded = JSON.stringify(selectedLocator);
        for (const tab of view.tabs || []) {
          if (tab !== active) render(tab);
          const target = [...drawer.querySelectorAll("[data-locator]")].find(
            (node) => node.dataset.locator === encoded,
          );
          if (target) {
            target.click();
            break;
          }
        }
      }
      drawer.focus();
    })
    .catch(() => {
      const errorHeader = el("header", "", { class: "artifact-header" });
      errorHeader.append(el("h2", "Artifact 不可用"), close);
      drawer.replaceChildren(
        errorHeader,
        notice("failure", "无法读取 Artifact", "服务未返回可检查的安全投影。"),
      );
      drawer.focus();
    });
}
function documents() {
  const main = el("main", "", { class: "documents-page" }),
    surface = el("section", "", {
      class: "documents-surface",
      "aria-labelledby": "documents-list-title",
      "aria-live": "polite",
    }),
    current = el("section", "", {
      class: "documents-current",
      "aria-labelledby": "current-submission-title",
      "aria-live": "polite",
      hidden: "",
    }),
    header = heading("文档", "已持久化的提交、处理状态与诊断入口"),
    commands = el("div", "", { class: "documents-commands" }),
    open = button("", () => showDialog()),
    refresh = iconButton("refresh", "刷新文档列表", () => load(false));
  open.className = "command-link command-primary";
  open.append(icon("upload"), el("span", "上传并预检"));
  commands.append(refresh, open);
  header.classList.add("documents-title");
  header.append(commands);
  main.append(header, surface, current);
  shell(main);
  let generation = 0,
    items = [],
    nextCursor = null,
    mode = "loading";
  const byteLabel = (value) =>
    value < 1024
      ? `${value} B`
      : value < 1024 * 1024
        ? `${(value / 1024).toFixed(value < 10240 ? 1 : 0)} KB`
        : `${(value / 1024 / 1024).toFixed(1)} MB`;
  const runHref = (id) => {
    const p = new URLSearchParams({ run: id, legacy: "ingestion" });
    if (workspaceId) p.set("workspace", workspaceId);
    return `/workbench/runs?${p}`;
  };
  const renderList = () => {
    surface.replaceChildren(
      el("h2", "已上传文档", { id: "documents-list-title", class: "sr-only" }),
    );
    surface.setAttribute(
      "aria-busy",
      String(mode === "loading" || mode === "more"),
    );
    if (mode === "loading") {
      const loading = skeletonRows(6);
      loading.classList.add("document-list-loading");
      surface.append(loading);
      return;
    }
    if (mode === "error") {
      surface.append(
        notice("failure", "无法加载文档列表", "已上传文档暂时不可用。", [
          button("重试", () => load(false)),
        ]),
      );
      return;
    }
    if (!items.length) {
      surface.append(
        emptyState(
          "尚无已上传文档",
          "完成预检并创建 Run 后，持久化的文档提交会显示在这里。",
        ),
      );
      return;
    }
    const wrap = el("div", "", {
        class: "document-table-wrap",
        tabindex: "0",
        role: "region",
        "aria-label": "已上传文档表格",
      }),
      table = el("table", "", {
        class: "document-table",
        "aria-label": "已上传文档",
      }),
      head = el("thead"),
      headRow = el("tr");
    [
      "文档",
      "格式",
      "处理类别",
      "Ingestion Profile",
      "最近 Run",
      "状态",
      "操作",
    ].forEach((value) => headRow.append(el("th", value, { scope: "col" })));
    head.append(headRow);
    const body = el("tbody");
    for (const row of items) {
      const tr = el("tr"),
        identity = el("div", "", { class: "document-identity" }),
        name = el("strong", row.filename),
        meta = el("span", byteLabel(row.byteSize)),
        source = el("code", row.sourceArtifactId);
      identity.append(name, meta, source);
      const run = row.latestRun
          ? el("a", row.latestRun.id, {
              href: runHref(row.latestRun.id),
              class: "document-run-link",
            })
          : el("span", "不可用", { class: "muted" }),
        actions = el("div", "", { class: "document-actions" });
      if (row.actions?.sourceArtifactId)
        actions.append(
          iconButton("file", "检查 Source Artifact", (event) =>
            inspector(row.actions.sourceArtifactId, event.currentTarget),
          ),
        );
      if (row.actions?.outputArtifactId)
        actions.append(
          iconButton("search", "检查最新输出 Artifact", (event) =>
            inspector(row.actions.outputArtifactId, event.currentTarget),
          ),
        );
      const state = row.latestRun?.state || "PENDING",
        tone = state === "PENDING" ? "neutral" : statusTone(state);
      [
        identity,
        row.format || row.mediaType || "不可用",
        row.documentClass || "不可用",
        row.profileId || "不可用",
        run,
        statusTag(statusLabel(state), tone),
        actions,
      ].forEach((value) => {
        const td = el("td");
        td.append(
          value instanceof Node
            ? value
            : document.createTextNode(String(value)),
        );
        tr.append(td);
      });
      body.append(tr);
    }
    table.append(head, body);
    wrap.append(table);
    surface.append(wrap);
    const footer = el("footer", "", { class: "document-page-actions" });
    if (mode === "more-error") {
      footer.append(
        notice("failure", "无法加载更多文档", "已显示的文档保持不变。", [
          button("重试", () => load(true)),
        ]),
      );
    } else if (nextCursor) {
      footer.append(
        button(
          mode === "more" ? "正在加载…" : "加载更多",
          () => load(true),
          mode === "more",
        ),
      );
    }
    surface.append(footer);
  };
  const load = async (append) => {
    const requestGeneration = append ? generation : ++generation;
    if (!append) {
      items = [];
      nextCursor = null;
      mode = "loading";
    } else mode = "more";
    renderList();
    try {
      const suffix = new URLSearchParams({ limit: "25" });
      if (append && nextCursor) suffix.set("cursor", nextCursor);
      const result = await api(`/api/workbench/documents?${suffix}`);
      if (requestGeneration !== generation) return;
      const incoming = result.items || [],
        known = new Set(items.map((item) => item.sourceArtifactId));
      if (
        incoming.some((item) => known.has(item.sourceArtifactId)) ||
        new Set(incoming.map((item) => item.sourceArtifactId)).size !==
          incoming.length
      )
        throw new Error("DOCUMENT_LIST_DUPLICATE");
      items = append ? [...items, ...incoming] : incoming;
      nextCursor = result.page?.nextCursor || null;
      mode = "ready";
    } catch {
      if (requestGeneration !== generation) return;
      mode = append ? "more-error" : "error";
    } finally {
      if (requestGeneration === generation) renderList();
    }
  };
  const renderCurrent = (p, fileName) => {
    const row = el("div", "", { class: "document-current" }),
      selected = p.selection?.profileId || p.automatic?.selectedProfileId;
    row.append(
      icon("file"),
      definitionRows(
        [
          ["文件 / Source", fileName || p.sourceArtifactId],
          ["媒体类型", p.detected?.media_type],
          [
            "大小",
            p.detected?.byte_size != null
              ? `${p.detected.byte_size} bytes`
              : null,
          ],
          ["选中 Profile", selected],
          ["计划摘要", p.planDigest],
        ],
        "document-facts",
      ),
    );
    current.hidden = false;
    current.replaceChildren(
      sectionHeader("current-submission-title", "本次提交", "预检完成"),
      row,
    );
  };
  const showDialog = (handoff = null) => {
    const modal = createDialogShell("上传并预检", open),
      dialog = modal.dialog,
      head = el("header", "", { class: "dialog-header" }),
      body = el("div", "", { class: "upload-dialog-body" }),
      foot = el("footer", "", { class: "dialog-actions" }),
      close = iconButton("close", "关闭上传对话框", modal.dismiss),
      profile = el("input", "", {
        placeholder: "Ingestion Profile Set ID",
        "aria-label": "Ingestion Profile Set ID",
      }),
      file = el("input", "", { type: "file", "aria-label": "选择文档" }),
      result = el("div", "", {
        class: "preflight-result",
        "aria-live": "polite",
      }),
      alert = el("div", "", {
        class: "preflight-alert",
        "aria-live": "assertive",
      }),
      requestStatus = el("p", "", {
        class: "preflight-request-status",
        role: "status",
        "aria-live": "polite",
      }),
      headCopy = el("div"),
      fileLabel = el("label", "文档"),
      profileLabel = el("label", "Profile Set"),
      source = el("section", "", { class: "upload-source-step" });
    let generation = 0,
      currentPreview = null,
      replacementToken = null;
    const cancel = () => button("取消", modal.dismiss),
      resetCurrent = (message) => {
        current.hidden = false;
        current.replaceChildren(
          sectionHeader(
            "current-submission-title",
            "本次提交",
            "API 支持的当前选择",
          ),
          emptyState(
            message || "尚未选择文档",
            message
              ? "等待服务返回新的固定计划。"
              : "上传后将在这里显示当前预检与固定计划信息。",
          ),
        );
      };
    const clearPreview = () => {
      generation += 1;
      if (currentPreview?.token) replacementToken = currentPreview.token;
      currentPreview = null;
      result.replaceChildren();
      alert.replaceChildren();
      requestStatus.textContent = "";
      foot.replaceChildren(cancel());
      preflight.disabled = false;
      resetCurrent();
    };
    const render = async (p, fileName) => {
      currentPreview = p;
      if (!profile.value && p.workspaceProfileId)
        profile.value = p.workspaceProfileId;
      const automatic = p.automatic || {},
        selected = p.selection?.profileId || automatic.selectedProfileId,
        candidates = automatic.candidateProfileIds || [selected],
        resolution = el("fieldset", "", { class: "profile-resolution" });
      resolution.append(el("legend", "Profile 解析依据"));
      for (const id of candidates.filter(Boolean)) {
        const radio = el("input", "", {
          type: "radio",
          name: "ingestion-profile",
          value: id,
          "aria-label": `选择 Profile ${id}`,
        });
        radio.checked = id === selected;
        const label = el("label", "", { class: "profile-option" }),
          descriptor =
            id === automatic.selectedProfileId
              ? statusTag("自动选中", "info")
              : id === selected
                ? statusTag("当前预览", "success")
                : el("span", "显式候选", { class: "muted" });
        label.append(radio, el("strong", id), descriptor);
        resolution.append(label);
        radio.addEventListener("change", async () => {
          if (!radio.checked || id === selected) return;
          const requestGeneration = ++generation,
            token = p.token;
          currentPreview = null;
          replacementToken = null;
          result.replaceChildren();
          alert.replaceChildren();
          foot.replaceChildren(cancel());
          requestStatus.textContent = "正在切换 Profile 预览…";
          preflight.disabled = true;
          resetCurrent("正在切换 Profile 预览");
          try {
            const next = await api(
              `/api/workbench/documents/preflights/${token}/selection`,
              {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({ profileId: id }),
              },
            );
            if (requestGeneration !== generation) return;
            await render(next, fileName);
            requestStatus.textContent = "Profile 预览已更新";
          } catch {
            if (requestGeneration !== generation) return;
            requestStatus.textContent = "Profile 预览切换失败，请重新预检";
            alert.replaceChildren(
              notice(
                "failure",
                "无法切换 Profile",
                "旧预检已失效，请重新预检后再提交。",
              ),
            );
          } finally {
            if (requestGeneration === generation) preflight.disabled = false;
          }
        });
      }
      const matched =
        (automatic.evaluatedRules || [])
          .map(
            (rule) =>
              `${rule.rule_id || rule.ruleId || "规则"}：${rule.matched ? "匹配" : "未匹配"}`,
          )
          .join("；") || "未返回规则评估";
      resolution.append(
        definitionRows([
          ["选择层级", p.selection?.selectionTier || automatic.selectionTier],
          ["候选 Profile", candidates.join(", ")],
          ["规则评估", matched],
          ["最终 Profile", selected],
        ]),
      );
      const facts = definitionRows(
          Object.entries(p.detected || {}).map(([key, value]) => [key, value]),
        ),
        factSection = el("section", "", { class: "preflight-facts" });
      factSection.append(el("h3", "检测事实"), facts);
      const stages = el("section", "", { class: "resolved-stages" });
      stages.append(el("h3", "解析后的阶段"));
      for (const stage of p.stages || []) {
        const row = el("div", "", { class: "resolved-stage-row" });
        row.append(
          el("strong", stage.key),
          el(
            "span",
            (stage.candidates || [])
              .map((candidate) => candidate.pluginId)
              .join(", ") || "Plugin 不可用",
          ),
        );
        stages.append(row);
      }
      const disclosure = el("section", "", { class: "persistence-disclosure" }),
        external = p.disclosure?.externalStages || [],
        ack = el("input", "", {
          type: "checkbox",
          "aria-label": "确认外部阶段披露",
        });
      disclosure.append(
        notice(
          "info",
          "本地持久化",
          p.disclosure?.localPersistence || "持久化信息不可用。",
        ),
      );
      if (external.length) {
        const warning = notice(
            "warning",
            "外部阶段披露",
            "以下已选阶段可能向外部提供方发送内容。",
          ),
          list = el("ul");
        for (const item of external)
          list.append(
            el(
              "li",
              `${item.stage} / ${item.pluginId || "Plugin 不可用"} / ${item.capability || "能力不可用"}：${item.message || "披露信息不可用"}`,
            ),
          );
        warning.lastChild.append(list);
        const label = el("label", "", { class: "acknowledgement" });
        label.append(ack, el("span", "确认已了解外部阶段披露"));
        disclosure.append(warning, label);
      }
      const run = button(
        "创建新 Run",
        async () => {
          if (currentPreview !== p) return;
          run.disabled = true;
          try {
            const receipt = await api(
              `/api/workbench/documents/preflights/${p.token}/runs`,
              {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({
                  profileId: selected,
                  acknowledgeExternal: ack.checked,
                }),
              },
            );
            location.href =
              href("runs") + `?run=${receipt.runId}&legacy=ingestion`;
          } catch {
            alert.replaceChildren(
              notice("failure", "无法创建 Run", "预检令牌或确认状态无效。"),
            );
            run.disabled = external.length > 0 && !ack.checked;
          }
        },
        external.length > 0,
      );
      ack.addEventListener("change", () => (run.disabled = !ack.checked));
      foot.replaceChildren(cancel(), run);
      result.replaceChildren(
        factSection,
        resolution,
        stages,
        definitionRows([
          ["Profile Set", p.workspaceProfileId || profile.value],
          ["计划摘要", p.planDigest],
          ["复用 Source Artifact", p.sourceArtifactId],
        ]),
        disclosure,
      );
      renderCurrent(p, fileName);
    };
    const preflight = button("预检", async () => {
      const selectedFile = file.files?.[0];
      if (!selectedFile || !profile.value) return;
      const oldToken = currentPreview?.token || replacementToken,
        requestGeneration = ++generation;
      currentPreview = null;
      replacementToken = null;
      result.replaceChildren();
      alert.replaceChildren();
      foot.replaceChildren(cancel());
      resetCurrent("正在预检");
      preflight.disabled = true;
      requestStatus.textContent = "正在预检…";
      const headers = {
        "X-Profile-Id": profile.value,
        "X-Filename": selectedFile.name,
        "Content-Type": selectedFile.type || "application/octet-stream",
      };
      if (oldToken) headers["X-Replaces-Preflight-Token"] = oldToken;
      try {
        const next = await api("/api/workbench/documents/preflight", {
          method: "PUT",
          headers,
          body: selectedFile,
        });
        if (requestGeneration !== generation) return;
        await render(next, selectedFile.name);
        requestStatus.textContent = "预检完成";
      } catch {
        if (requestGeneration !== generation) return;
        requestStatus.textContent = "预检失败，可重试";
        alert.replaceChildren(
          notice("failure", "预检失败", "请检查 Profile Set 和文档后重试。"),
        );
      } finally {
        if (requestGeneration === generation) preflight.disabled = false;
      }
    });
    profile.addEventListener("input", clearPreview);
    file.addEventListener("change", clearPreview);
    headCopy.append(
      el("span", "NEW INGESTION", { class: "eyebrow" }),
      el("h2", "上传并预检文档"),
    );
    head.append(headCopy, close);
    fileLabel.append(file);
    profileLabel.append(profile);
    source.append(fileLabel, profileLabel, preflight, requestStatus);
    body.append(source, result, alert);
    foot.append(cancel());
    dialog.append(head, body, foot);
    if (handoff) {
      profile.value = handoff.workspaceProfileId || "";
      file.disabled = true;
      source.insertBefore(
        notice(
          "info",
          "复用 Source Artifact",
          handoff.sourceArtifactId || "Source Artifact 不可用。",
        ),
        file.closest("label"),
      );
      render(handoff, handoff.sourceArtifactId);
    }
    modal.focus();
  };
  const handoff = sessionStorage.getItem("kb2.rerun-preflight");
  if (handoff) {
    sessionStorage.removeItem("kb2.rerun-preflight");
    showDialog(JSON.parse(handoff));
  }
  load(false);
}
const unavailable=value=>value==null||value===''?'不可用':String(value);
const identityList=value=>Array.isArray(value)&&value.length?value.join('、'):'不可用';
const definitionList=(facts,className='definition-grid')=>{const list=el('dl','',{class:className});for(const [name,value] of facts){list.append(el('dt',name),el('dd',unavailable(value)))}return list};
const field=(label,value,onInput,{multiline=false,type='text'}={})=>{const wrap=el('label','',{class:'field'}),control=el(multiline?'textarea':'input','',{'aria-label':label,type});control.value=value??'';control.addEventListener('input',()=>onInput(control.value));wrap.append(el('span',label),control);return wrap};

function queryLab() {
  const requestedRun = new URL(location).searchParams.get("run"),
    validRequestedRun =
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        requestedRun || "",
      )
        ? requestedRun
        : null,
    main = el("main", "", { class: "query-page" }),
    workspace = el("section", "", {
      class: "query-workspace",
      "aria-label": "Query Lab 工作区",
    }),
    control = el("aside", "", { class: "query-control-pane" }),
    retrieval = el("section", "", { class: "query-retrieval-pane" }),
    answer = el("aside", "", { class: "query-answer-pane" }),
    question = el("textarea", "", {
      placeholder: "输入问题",
      "aria-label": "问题",
      maxlength: "8192",
    }),
    profile = el("select", "", { "aria-label": "已保存 Query Profile" }),
    index = el("select", "", { "aria-label": "已索引 Artifact" }),
    status = el("div", "加载 Query Lab 选项…", {
      class: "query-status",
      role: "status",
      "aria-live": "polite",
    }),
    preview = el("div"),
    stopHost = el("div", "", { class: "query-stop-host" }),
    runButton = button("预检", () => preflight(), true);
  let timer = null,
    last = null,
    requestVersion = 0,
    pollVersion = 0,
    pending = false;
  const reset = (invalidate = true) => {
    clearTimeout(timer);
    if (invalidate) {
      requestVersion++;
      pending = false;
      [question, profile, index].forEach((x) => (x.disabled = false));
      status.textContent = "输入已更改，请重新预检。";
    }
    last = null;
    stopHost.replaceChildren();
    preview.replaceChildren();
    retrieval.replaceChildren(
      emptyState(
        "尚无检索 Trace",
        "完成预检并创建 Query Run 后显示有序阶段与候选。",
      ),
    );
    answer.replaceChildren(
      emptyState("尚无最终结果", "最终状态与 Evidence 将由 Query Run 返回。"),
    );
    runButton.textContent = "预检";
    runButton.disabled =
      pending || !question.value.trim() || !profile.value || !index.value;
  };
  [question, profile, index].forEach((node) =>
    node.addEventListener(node === question ? "input" : "change", reset),
  );
  const tableRegion = (table, label) => {
    table.tabIndex = 0;
    table.setAttribute("role", "region");
    table.setAttribute("aria-label", label);
    return table;
  };
  const candidateTable = (c) => {
    const rows = (c.rows || []).map((row) => {
      const contributions = (row.contributions || []).map(
          (item) =>
            `${item.contributorId ?? "不可用"} #${item.originalRank ?? "不可用"} / ${item.safeScore ?? "不可用"} (${item.scoreKind ?? "不可用"})`,
        ),
        decision = row.decision;
      return [
        row.rank ?? "不可用",
        row.documentLabel || "文档不可用",
        row.excerpt || "摘录不可用",
        row.safeScore ?? "不可用",
        identityList(contributions),
        row.locatorLabel || "定位不可用",
        decision
          ? `${decision.reason} / ${decision.input_rank}->${decision.output_rank ?? "excluded"}`
          : "不可用",
      ];
    });
    return rows.length
      ? tableRegion(denseTable(
          [
            "排名",
            "文档",
            "摘录",
            "安全分数",
            "贡献明细",
            "Locator",
            "Rerank 决策",
          ],
          rows,
          `${c.stageId} 候选`,
        ), `${c.stageId} 候选横向滚动区`)
      : emptyState(
          c.available ? "没有候选" : "候选 Artifact 不可用",
          "该阶段没有返回可展示候选。",
        );
  };
  const renderCandidates = (candidates) => {
    const host = el("section", "", { class: "candidate-region" });
    host.append(el("h3", "候选与决策"));
    if (!candidates.length) {
      host.append(emptyState("没有候选集合", "运行未返回候选 Artifact。"));
      return host;
    }
    const tabs = el("div", "", {
        class: "candidate-tabs",
        role: "tablist",
        "aria-label": "候选集合",
      }),
      panel = el("div", "", { class: "candidate-panel" });
    let selected = 0;
    const select = (i) => {
      selected = i;
      [...tabs.children].forEach((tab, n) => {
        tab.setAttribute("aria-selected", String(n === i));
        tab.tabIndex = n === i ? 0 : -1;
      });
      panel.replaceChildren(candidateTable(candidates[i]));
    };
    candidates.forEach((c, i) => {
      const tab = button(c.stageId, () => select(i));
      tab.id = `candidate-tab-${i}`;
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-controls", "candidate-panel");
      tab.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
          return;
        event.preventDefault();
        const next =
          event.key === "Home"
            ? 0
            : event.key === "End"
              ? candidates.length - 1
              : (selected +
                  (event.key === "ArrowRight" ? 1 : -1) +
                  candidates.length) %
                candidates.length;
        select(next);
        tabs.children[next].focus();
      });
      tabs.append(tab);
    });
    panel.id = "candidate-panel";
    panel.setAttribute("role", "tabpanel");
    host.append(tabs, panel);
    select(0);
    return host;
  };
  const detailKind = (d) => d.kind || "不可用";
  const contextProjection = (details) => {
    const decisions = [],
      shortages = [];
    for (const detail of details || []) {
      if (detailKind(detail) !== "context") continue;
      for (const decision of detail.decisions || []) decisions.push(decision);
      if (detail.shortage) shortages.push(detail.shortage);
    }
    return {
      decisions,
      rows: decisions.map((decision) => [
        decision.chunk_id ?? "不可用",
        decision.source_rank ?? "不可用",
        decision.reason ?? "不可用",
        decision.safe_score ?? "不可用",
      ]),
      shortages,
    };
  };
  const decisionPath = (path) => {
    const columns = path?.columns || [],
      rows = path?.rows || [];
    if (!rows.length)
      return emptyState(
        "没有决策路径",
        "运行未返回可关联的候选与 Context 决策。",
      );
    const headers = [
        "文档 / Chunk",
        ...columns.map((x) => x.stageId),
        "摘录 / Locator",
      ],
      values = rows.map((row) => [
        `${row.documentLabel || "文档不可用"}\n${row.chunkId || "Chunk 不可用"}`,
        ...columns.map((column) => {
          const stage = row.stages?.[column.stageId] || {
            state: "NOT_PRESENT",
          };
          if (stage.state === "NOT_PRESENT") return "未出现";
          if (column.kind === "context")
            return `${stage.reason || "不可用"} / #${stage.source_rank ?? "不可用"} / ${stage.safe_score ?? "不可用"}`;
          const decision = stage.decision ? ` / ${stage.decision.reason}` : "";
          return `#${stage.rank ?? "不可用"} / ${stage.safeScore ?? "不可用"}${decision}`;
        }),
        `${row.excerpt || "摘录不可用"}\n${row.locatorLabel || "定位不可用"}`,
      ]);
    return tableRegion(denseTable(headers, values, "候选决策路径"), "候选决策路径横向滚动区");
  };
  const attemptDetails = (stages) => {
    const host = el("section", "", { class: "query-attempt-details" });
    host.append(el("h3", "阶段技术详情"));
    for (const s of stages) {
      const details = el("details", "", { class: "query-attempt" });
      details.append(
        el("summary", `${s.stageKey} #${s.attempt}`),
        definitionList([
          ["开始", formatTime(s.startedAt)],
          ["结束", formatTime(s.endedAt)],
          ["输入 Artifact", identityList((s.inputs || []).map((x) => x.id))],
          ["输出 Artifact", identityList((s.outputs || []).map((x) => x.id))],
          ["Metrics", signalValue(s.metrics)],
          ["Quality", signalValue(s.quality)],
        ]),
      );
      host.append(details);
    }
    return host;
  };
  const renderRun = (x) => {
    clearTimeout(timer);
    last = x;
    stopHost.replaceChildren();
    retrieval.replaceChildren(
      sectionHeader(
        "query-trace-title",
        "有序执行 Trace",
        `${(x.stages || []).length} 个阶段`,
      ),
    );
    const stages = (x.stages || []).map((s) => [
      s.stageKey,
      `#${s.attempt}`,
      statusTag(statusLabel(s.state), statusTone(s.state)),
      s.pluginId || "不可用",
      s.durationMs == null ? "不可用" : `${s.durationMs} ms`,
      s.failure?.code || "无",
    ]);
    retrieval.append(
      stages.length
        ? denseTable(
            ["阶段", "尝试", "状态", "Plugin", "耗时", "失败"],
            stages,
            "Query 有序阶段",
          )
        : emptyState("没有阶段 Trace", "运行未返回可展示阶段。"),
      renderCandidates(x.candidates || []),
      el("h3", "决策路径"),
      decisionPath(x.decisionPath),
      attemptDetails(x.stages || []),
    );
    const context = contextProjection(x.details);
    retrieval.append(
      el("h3", "Context Shortage"),
      context.shortages.length
        ? definitionList(
            context.shortages.flatMap((shortage, i) => [
              [`Shortage ${i + 1}`, shortage.reason],
              [
                "Minimum items",
                shortage.minimum_items ?? shortage.minimumItems,
              ],
              [
                "Selected items",
                shortage.selected_items ?? shortage.selectedItems,
              ],
              [
                "Selected tokens",
                shortage.selected_tokens ?? shortage.selectedTokens,
              ],
            ]),
          )
        : emptyState("没有 Context Shortage", "运行未返回 shortage 状态。"),
    );
    if (!x.final) {
      answer.replaceChildren(
        emptyState(
          x.terminalState ? "最终结果不可用" : "Query Run 正在执行",
          x.terminalState ? "运行未返回可验证的 FinalResponse。" : "最终状态与 Evidence 将在运行完成后显示。",
        ),
      );
      const runState = x.terminalState ? statusLabel(x.state) : "正在运行";
      status.textContent = validRequestedRun === x.id ? `Query Run ${x.id} / ${runState}` : `Query Run ${runState}`;
      status.className = "query-status";
      if (x.actions?.stop && !x.terminalState) {
        const stop = button("停止", async () => {
          stop.disabled = true;
          status.textContent = "正在停止 Query Run…";
          try {
            await api(`/api/workbench/query-runs/${x.id}/stop`, { method: "POST" });
            await load();
          } catch {
            status.textContent = "停止请求失败，可重试。";
            stop.disabled = false;
          }
        });
        stopHost.replaceChildren(stop);
      }
      if (!x.terminalState && x.state !== "FAILED") timer = setTimeout(load, 1000);
      return;
    }
    const final = x.final,
      tone =
        final.state === "ANSWERED"
          ? "success"
          : final.state === "FAILED"
            ? "failure"
            : "warning",
      band = el("section", "", { class: `final-state final-${tone}` });
    band.append(
      el("span", "权威最终状态", { class: "eyebrow" }),
      statusTag(final.state, tone),
      el("h2", final.state === "ANSWERED" ? "已验证答案" : "安全结果"),
    );
    if (final.state === "ANSWERED" && final.answer) {
      band.append(el("p", final.answer, { class: "answer-copy" }));
      const citations = el("div", "", { class: "citation-actions" });
      for (const key of final.citationKeys || []) {
        const item = (x.evidence || []).find((e) => e.citationKey === key);
        if (item?.sourceArtifactId)
          citations.append(
            button(key, (e) =>
              inspector(
                item.sourceArtifactId,
                e.currentTarget,
                item.sourceLocator,
              ),
            ),
          );
      }
      band.append(citations);
    } else band.append(el("p", final.action || "结果不可用，未发布答案。"));
    answer.replaceChildren(band, el("h3", "Evidence"));
    if (!(x.evidence || []).length)
      answer.append(
        emptyState("没有 Evidence", "该最终状态未返回可展示 Evidence。"),
      );
    for (const item of x.evidence || []) {
      const decision = item.contextDecision || {},
        row = el("article", "", { class: "evidence-row" }),
        head = el("header"),
        contributors = (item.contributors || []).map(
          (c) =>
            `${c.contributor_id ?? c.contributorId ?? "不可用"} / ${c.safe_score ?? c.safeScore ?? "不可用"}`,
        );
      head.append(
        el("strong", item.citationKey || "不可用"),
        el("span", item.documentLabel || "文档不可用"),
        statusTag(decision?.reason || "Context 决策不可用", "neutral"),
      );
      const actions = el("div", "", { class: "evidence-actions" });
      if (item.sourceArtifactId && item.sourceLocator)
        actions.append(
          button("源预览", (e) =>
            inspector(item.sourceArtifactId, e.currentTarget, item.sourceLocator),
          ),
        );
      else actions.append(el("span", "源预览不可用", { class: "muted" }));
      const details = el("details", "", { class: "evidence-details" });
      details.append(
        el("summary", "技术详情"),
        definitionList([
          ["Document ID", item.documentId],
          ["Chunk ID", item.chunkId],
          ["结构化 Locator", item.sourceLocator ? JSON.stringify(item.sourceLocator) : identityList(item.locators)],
          ["贡献者 / safe_score", identityList(contributors)],
          ["决策来源排名", decision?.source_rank],
          ["决策安全分数", decision?.safe_score],
          ["层级", identityList(item.hierarchy)],
          ["表格元素", identityList(item.tableElementIds)],
        ]),
      );
      row.append(
        head,
        el("p", item.excerpt || "不可用"),
        definitionList([
          ["Locator", item.locatorLabel],
          ["贡献者", identityList(contributors)],
          ["决策理由", decision?.reason],
        ]),
        actions,
        details,
      );
      answer.append(row);
    }
    const trace = (x.details || []).filter(
      (d) => detailKind(d) === "verification",
    );
    answer.append(el("h3", "验证与有限修复"));
    if (trace.length)
      for (const [i, d] of trace.entries()) {
        const details = el("details", "", { class: "verification-attempt" });
        details.append(el("summary", `Verification #${i + 1} / ${d.outcome || "不可用"}`), definitionList([["Failure codes", identityList(d.failureCodes)], ["Missing citation keys", identityList(d.missingCitationKeys)]]));
        answer.append(details);
      }
    else answer.append(emptyState("没有验证详情", "运行未返回 VerificationResult。"));
    const runState = x.terminalState ? statusLabel(x.state) : "正在运行";
    status.textContent =
      validRequestedRun === x.id
        ? `Query Run ${x.id} / ${runState}`
        : `Query Run ${runState}`;
    status.className = "query-status";
    if (x.actions?.stop && !x.terminalState) {
      const stop = button("停止", async () => {
        stop.disabled = true;
        status.textContent = "正在停止 Query Run…";
        try {
          await api(`/api/workbench/query-runs/${x.id}/stop`, {
            method: "POST",
          });
          await load();
        } catch {
          status.textContent = "停止请求失败，可重试。";
          stop.disabled = false;
        }
      });
      stopHost.replaceChildren(stop);
    }
    if (!x.terminalState && x.state !== "FAILED")
      timer = setTimeout(load, 1000);
  };
  const load = async () => {
    if (!last?.id) return;
    const id = last.id,
      version = requestVersion,
      poll = ++pollVersion;
    status.textContent = "正在读取 Query Run…";
    try {
      const result = await api(`/api/workbench/query-runs/${id}`);
      if (version === requestVersion && poll === pollVersion && last?.id === id)
        renderRun(result);
    } catch {
      if (
        version === requestVersion &&
        poll === pollVersion &&
        last?.id === id
      ) {
        status.replaceChildren(
          el("span", `Query Run ${id} 不存在或不可用。`),
          button("重试读取", load),
        );
        status.setAttribute("role", "alert");
      }
    }
  };
  const preflight = async () => {
    const version = ++requestVersion;
    pending = true;
    reset(false);
    [question, profile, index, runButton].forEach((x) => (x.disabled = true));
    status.textContent = "正在解析 Query Profile…";
    try {
      const p = await api("/api/workbench/query-lab/preflights", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          question: question.value,
          profileId: profile.value,
          indexId: index.value,
        }),
      });
      if (version !== requestVersion) return;
      const plan = el("section", "", { class: "query-preflight" }),
        stageRows = (p.stages || []).map((s) => [
          s.stageId,
          s.kind,
          s.pluginId,
        ]);
      plan.append(
        el("h2", "已解析计划"),
        definitionList([["Plan digest", p.planDigest]]),
        stageRows.length
          ? denseTable(
              ["阶段", "类型", "Plugin"],
              stageRows,
              "已解析 Query 计划",
            )
          : emptyState("计划无阶段", "服务未返回可执行阶段。"),
      );
      const ack = el("input", "", {
          type: "checkbox",
          "aria-label": "确认外部阶段披露",
        }),
        external = p.disclosure?.externalStages || [],
        submit = button(
          "创建 Query Run",
          async () => {
            const submitVersion = requestVersion;
            submit.disabled = true;
            status.textContent = "正在创建 Query Run…";
            try {
              const r = await api(
                `/api/workbench/query-lab/preflights/${p.token}/runs`,
                {
                  method: "POST",
                  headers: { "content-type": "application/json" },
                  body: JSON.stringify({ acknowledgeExternal: ack.checked }),
                },
              );
              if (submitVersion !== requestVersion) return;
              last = { id: r.runId };
              await load();
            } catch {
              if (submitVersion !== requestVersion) return;
              status.textContent = "Query Run 创建失败，可重试或重新预检。";
              submit.disabled = external.length > 0 && !ack.checked;
            }
          },
          external.length > 0,
        );
      if (external.length) {
        const disclose = notice(
          "warning",
          "外部生成边界",
          `所选计划包含外部阶段：${external.map((x) => x.stage || x.stageId || x.capability).join("、")}。`,
        );
        const label = el("label", "", { class: "acknowledgement" });
        label.append(ack, el("span", "确认外部阶段披露"));
        ack.addEventListener("change", () => (submit.disabled = !ack.checked));
        plan.append(disclose, label);
      }
      plan.append(submit);
      preview.replaceChildren(plan);
      status.textContent = "预检完成，可创建 Query Run。";
    } catch {
      if (version === requestVersion) {
        preview.replaceChildren(
          notice("failure", "预检失败", "Query Profile 或索引当前不可用。"),
        );
        status.textContent = "预检失败，输入与选择已保留。";
      }
    } finally {
      if (version === requestVersion) {
        pending = false;
        [question, profile, index].forEach((x) => (x.disabled = false));
        runButton.disabled =
          !question.value.trim() || !profile.value || !index.value;
      }
    }
  };
  const controls = el("div", "", { class: "query-control-fields" });
  controls.append(
    el("label", "问题"),
    question,
    el("label", "Query Profile"),
    profile,
    el("label", "已索引 Artifact"),
    index,
    runButton,
    status,
    stopHost,
    preview,
  );
  control.append(
    sectionHeader("query-control-title", "执行控制", "服务权威"),
    controls,
  );
  workspace.append(control, retrieval, answer);
  main.append(
    heading("Query Lab", "执行固定 Query Profile 并检查 Evidence"),
    workspace,
  );
  shell(main);
  reset(false);
  api("/api/workbench/query-lab/options")
    .then((x) => {
      profile.replaceChildren();
      index.replaceChildren();
      if (!(x.profiles || []).length)
        profile.append(el("option", "没有可用 Query Profile", { value: "" }));
      else
        x.profiles.forEach((v) =>
          profile.append(el("option", v.profileId, { value: v.profileId })),
        );
      if (!(x.indexes || []).length)
        index.append(el("option", "没有可用索引 Artifact", { value: "" }));
      else
        x.indexes.forEach((v) =>
          index.append(
            el("option", `${v.id} / ${v.summary || "索引 Artifact"}`, {
              value: v.id,
            }),
          ),
        );
      status.textContent =
        !x.profiles?.length || !x.indexes?.length
          ? "没有可执行的 Query Profile 或索引。"
          : "Query Lab 已就绪。";
      reset(false);
      if (validRequestedRun) {
        last = { id: validRequestedRun };
        load();
      }
    })
    .catch(() => {
      status.textContent = "Query Lab 选项不可用。";
      status.setAttribute("role", "alert");
    });
}

function evaluationDataset() {
  const main = el("main", "", { class: "evaluation-dataset-page" }),
    filter = el("input", "", {
      placeholder: "筛选评估数据集",
      "aria-label": "筛选评估数据集",
    }),
    status = el("div", "正在加载评估数据集…", {
      class: "dataset-status",
      role: "status",
      "aria-live": "polite",
    }),
    catalog = el("aside", "", {
      class: "dataset-catalog",
      "aria-label": "评估数据集列表",
    }),
    detail = el("section", "", { class: "dataset-detail" }),
    casesHost = el("nav", "", {
      class: "dataset-case-list",
      "aria-label": "案例列表",
    }),
    editor = el("form", "", { class: "dataset-case-editor" }),
    layout = el("section", "", { class: "dataset-workspace" });
  let current = null,
    selected = null,
    pending = false,
    loadVersion = 0;
  const cases = () =>
    current
      ? [
          ...(current.content.annotations || []).map((x) => ({
            item: x,
            kind: "annotation",
          })),
          ...(current.content.query_cases || []).map((x) => ({
            item: x,
            kind: "query",
          })),
        ]
      : [];
  const lines = (value) => (Array.isArray(value) ? value.join("\n") : "");
  const setLines = (item, key, value) =>
    (item[key] = value
      .split("\n")
      .map((x) => x.trim())
      .filter(Boolean));
  const renderCaseList = () => {
    casesHost.replaceChildren(
      sectionHeader("dataset-cases-title", "案例", `${cases().length} 条`),
    );
    for (const entry of cases()) {
      const errors = current.validation?.[entry.item.id] || [],
        reviewed = (entry.item.reviews || []).length > 0,
        incomplete = errors.some((code) => String(code).includes("INCOMPLETE")),
        b = button("", () => {
          selected = entry;
          renderEditor();
        });
      b.setAttribute(
        "aria-pressed",
        String(selected?.item.id === entry.item.id),
      );
      b.className = "dataset-case-row";
      b.append(
        el("strong", entry.item.id),
        el("span", entry.kind === "query" ? "问题" : "文档"),
        statusTag(
          reviewed
            ? "已审核"
            : incomplete
              ? "不完整"
              : errors.length
                ? "无效"
                : "待审核",
          reviewed ? "success" : errors.length ? "failure" : "warning",
        ),
      );
      casesHost.append(b);
    }
    if (!cases().length)
      casesHost.append(
        emptyState("数据集为空", "此修订中没有标注或问题案例。"),
      );
  };
  const renderEditor = () => {
    editor.replaceChildren();
    if (!selected) {
      editor.append(
        emptyState("选择案例", "从案例列表中选择一个案例进行编辑。"),
      );
      return;
    }
    const item = selected.item,
      errors = current.validation?.[item.id] || [],
      reviewed = (item.reviews || []).length > 0;
    let locatorValid = true,
      locatorError = null;
    editor.append(
      sectionHeader(
        "case-editor-title",
        selected.kind === "query" ? "问题案例" : "文档标注",
        item.id,
      ),
      errors.length
        ? notice("failure", "案例验证失败", errors.join("、"))
        : notice(
            "info",
            reviewed ? "已显式审核" : "待审核",
            reviewed ? "审核记录已绑定当前内容。" : "保存后仍需显式审核。",
          ),
    );
    const source = el("fieldset"),
      sourceLegend = el("legend", "来源与 Provenance");
    source.append(
      sourceLegend,
      field("Source Artifact ID", item.source?.id, (v) => (item.source.id = v)),
      field(
        "Source digest",
        item.source?.content_digest,
        (v) => (item.source.content_digest = v),
      ),
      field(
        "Source schema",
        item.source?.schema_revision,
        (v) => (item.source.schema_revision = v),
      ),
      field(
        "Source type",
        item.source?.artifact_type,
        (v) => (item.source.artifact_type = v),
      ),
      field(
        "Provenance origin",
        item.provenance?.origin,
        (v) => (item.provenance.origin = v),
      ),
      field(
        "Provenance operation",
        item.provenance?.operation,
        (v) => (item.provenance.operation = v),
      ),
    );
    editor.append(source);
    const labels = el("fieldset"),
      legend = el(
        "legend",
        selected.kind === "query" ? "问题与标签" : "标注与标签",
      );
    labels.append(legend);
    if (selected.kind === "query") {
      labels.append(
        field("问题", item.question, (v) => (item.question = v), {
          multiline: true,
        }),
        field(
          "Answerability",
          item.answerability,
          (v) => (item.answerability = v),
        ),
        field(
          "预期事实（每行一项）",
          lines(item.expected_facts),
          (v) => setLines(item, "expected_facts", v),
          { multiline: true },
        ),
        field(
          "禁止事实（每行一项）",
          lines(item.forbidden_facts),
          (v) => setLines(item, "forbidden_facts", v),
          { multiline: true },
        ),
        field(
          "相关 Evidence ID（每行一项）",
          lines(item.relevant_evidence_ids),
          (v) => setLines(item, "relevant_evidence_ids", v),
          { multiline: true },
        ),
        field(
          "必需 Citation key（每行一项）",
          lines(item.required_citation_keys),
          (v) => setLines(item, "required_citation_keys", v),
          { multiline: true },
        ),
        field(
          "确定性答案",
          item.deterministic_answer,
          (v) => (item.deterministic_answer = v),
          { multiline: true },
        ),
      );
      const ensureEvidence = () =>
          (item.evidence ??= {
            id: "",
            content_digest: "",
            schema_revision: "v1",
            artifact_type: "evidence.set",
          }),
        evidence = el("fieldset");
      evidence.append(
        el("legend", "Evidence Source Artifact"),
        field(
          "Evidence Artifact ID",
          item.evidence?.id,
          (v) => (ensureEvidence().id = v),
        ),
        field(
          "Evidence digest",
          item.evidence?.content_digest,
          (v) => (ensureEvidence().content_digest = v),
        ),
        field(
          "Evidence schema",
          item.evidence?.schema_revision,
          (v) => (ensureEvidence().schema_revision = v),
        ),
        field(
          "Evidence type",
          item.evidence?.artifact_type,
          (v) => (ensureEvidence().artifact_type = v),
        ),
      );
      labels.append(evidence);
    } else {
      item.target ??= { kind: "element" };
      const target = item.target,
        locatorValue = target.locator ? JSON.stringify(target.locator) : "";
      locatorError = el("div", "", {
        class: "field-error",
        role: "alert",
        "aria-live": "polite",
      });
      const locatorField = field(
        "Target locator",
        locatorValue,
        (v) => {
          try {
            target.locator = v ? JSON.parse(v) : null;
            locatorValid = true;
            locatorError.textContent = "";
          } catch {
            locatorValid = false;
            locatorError.textContent =
              "Locator 必须是有效 JSON；当前文本已保留。";
          }
          sync();
        },
        { multiline: true },
      );
      labels.append(
        field("Target kind", target.kind, (v) => (target.kind = v)),
        field(
          "Target element ID",
          target.element_id,
          (v) => (target.element_id = v || null),
        ),
        field(
          "Target table ID",
          target.table_id,
          (v) => (target.table_id = v || null),
        ),
        field(
          "Target cell ID",
          target.cell_id,
          (v) => (target.cell_id = v || null),
        ),
        locatorField,
        locatorError,
        field(
          "Target start",
          target.start,
          (v) => (target.start = v === "" ? null : Number(v)),
          { type: "number" },
        ),
        field(
          "Target end",
          target.end,
          (v) => (target.end = v === "" ? null : Number(v)),
          { type: "number" },
        ),
        field("Label", item.label, (v) => (item.label = v), {
          multiline: true,
        }),
      );
    }
    editor.append(labels);
    const slices = el("fieldset"),
      sliceLegend = el("legend", "切片标签");
    slices.append(sliceLegend);
    for (const [key, value] of Object.entries(item.slices || {}))
      slices.append(field(key, value, (v) => (item.slices[key] = v)));
    editor.append(slices);
    const reviewer = el("input", "", {
        placeholder: "Reviewer ID",
        "aria-label": "Reviewer ID",
        maxlength: "128",
      }),
      save = button("验证并保存", async () => {
        if (!locatorValid) return;
        pending = true;
        sync();
        status.textContent = "正在验证并保存新草稿修订…";
        try {
          const r = await api(
            `/api/workbench/evaluation-datasets/${current.id}`,
            {
              method: "PUT",
              headers: { "content-type": "application/json" },
              body: JSON.stringify(current.content),
            },
          );
          if (r.dataset) {
            status.textContent = "草稿修订已保存。";
            await loadDataset(r.dataset);
          } else {
            current.validation = r.validation || { "/": ["DATASET_INVALID"] };
            status.textContent = "数据集验证未通过，编辑已保留。";
            renderCaseList();
            renderEditor();
          }
        } catch {
          status.textContent = "保存失败，编辑已保留。";
        } finally {
          pending = false;
          sync();
        }
      }),
      review = button(
        "标记已审核",
        async () => {
          pending = true;
          sync();
          status.textContent = "正在记录显式审核…";
          try {
            const r = await api(
              `/api/workbench/evaluation-datasets/${current.id}/revisions/${current.revision}/cases/${encodeURIComponent(item.id)}/review`,
              {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({ reviewer: reviewer.value }),
              },
            );
            if (r.dataset) {
              status.textContent = "案例已审核。";
              await loadDataset(r.dataset);
            } else status.textContent = r.code || "案例不可审核。";
          } catch {
            status.textContent = "审核失败，Reviewer ID 已保留。";
          } finally {
            pending = false;
            sync();
          }
        },
        reviewed || errors.length > 0,
      );
    reviewer.addEventListener("input", () => sync());
    const actions = el("div", "", { class: "editor-actions" });
    actions.append(save, reviewer, review);
    editor.append(actions);
    function sync() {
      [...editor.querySelectorAll("input,textarea,button")].forEach((x) => {
        if (x !== reviewer) x.disabled = pending;
      });
      save.disabled = pending || !locatorValid;
      review.disabled =
        pending || reviewed || errors.length > 0 || !reviewer.value.trim();
    }
  };
  const loadDataset = async (row) => {
    const version = ++loadVersion;
    status.textContent = "正在加载数据集修订…";
    try {
      const d = row.content
        ? row
        : await api(
            `/api/workbench/evaluation-datasets/${row.id}?revision=${row.revision}`,
          );
      if (version !== loadVersion) return;
      current = structuredClone(d);
      const all = cases(),
        choice =
          all.find(
            (x) =>
              x.item.provenance?.origin === "generated" &&
              !(x.item.reviews || []).length &&
              !(d.validation?.[x.item.id] || []).length,
          ) ||
          all.find((x) => !(x.item.reviews || []).length) ||
          all[0];
      selected = choice || null;
      detail.replaceChildren(
        el("header", "", { class: "dataset-detail-header" }),
        casesHost,
        editor,
      );
      detail.firstChild.append(
        el("h2", `评估数据集 / r${d.revision}`),
        definitionList([
          ["Dataset ID", d.id],
          ["Digest", d.digest],
          ["已审核", `${d.reviewedCount}/${d.caseCount}`],
          ["创建时间", formatTime(d.createdAt)],
        ]),
      );
      renderCaseList();
      renderEditor();
      status.textContent = "数据集修订已加载。";
    } catch {
      status.textContent = "数据集加载失败，可重新选择。";
      status.setAttribute("role", "alert");
    }
  };
  const refresh = async () => {
    status.textContent = "正在加载评估数据集…";
    try {
      const rows = await api(
        `/api/workbench/evaluation-datasets?q=${encodeURIComponent(filter.value)}`,
      );
      catalog.replaceChildren(filter);
      if (!rows.length) {
        current = null;
        selected = null;
        casesHost.replaceChildren();
        editor.replaceChildren();
        catalog.append(
          emptyState(
            filter.value ? "没有匹配数据集" : "尚无评估数据集",
            filter.value ? "调整筛选条件。" : "创建数据集后将在这里显示。",
          ),
        );
        detail.replaceChildren(
          emptyState("没有可编辑数据集", "当前目录没有结果。"),
        );
        status.textContent = "数据集目录为空。";
        return;
      }
      rows.forEach((row) => {
        const b = button("", () => loadDataset(row));
        b.className = "dataset-row";
        b.append(
          el("strong", `r${row.revision}`),
          el("span", `${row.reviewedCount}/${row.caseCount} 已审核`),
          el(
            "small",
            `${row.annotationCount} 标注 · ${row.queryCaseCount} 问题`,
          ),
          shortIdentity(row.digest, 12),
        );
        catalog.append(b);
      });
      status.textContent = `已加载 ${rows.length} 个数据集。`;
      if (!current) loadDataset(rows[0]);
    } catch {
      catalog.replaceChildren(
        filter,
        emptyState(
          "目录不可用",
          "重新加载以读取数据集。",
          button("重新加载", refresh),
        ),
      );
      status.textContent = "评估数据集目录不可用。";
      status.setAttribute("role", "alert");
    }
  };
  filter.addEventListener("input", refresh);
  layout.append(catalog, detail);
  main.append(
    heading("评估数据集", "维护受审核的文档标注与问题案例"),
    status,
    layout,
  );
  shell(main);
  refresh();
}

function evaluationRun(){
 const routeParams=new URL(location).searchParams,requestedCase=/^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/.test(routeParams.get('q')||'')?routeParams.get('q'):null,main=el('main','',{class:'evaluation-run-page'}),pick=el('select','',{'aria-label':'评估运行'}),status=el('div','正在加载 Evaluation Run…',{class:'evaluation-status',role:'status','aria-live':'polite'}),surface=el('section','',{class:'evaluation-run-surface'}),owners=['ingestion','retrieval','context','answer','citation','decision','judge','latency','resources'],ownerLabels={ingestion:'Ingestion',retrieval:'Retrieval',context:'Context',answer:'Answer',citation:'Citation',decision:'Decision',judge:'Judge',latency:'Latency',resources:'Resources'};
 const artifactButton=(label,value,locator=null)=>value?button(label,e=>inspector(value,e.currentTarget,locator)):el('span','不可用',{class:'muted'});
 const renderManifest=(x,manifest)=>{const section=el('details','',{class:'manifest-band',open:''}),summary=el('summary','不可变 Manifest');section.append(summary,definitionList([['Manifest Artifact',x.manifest?.artifactId],['Artifact digest',x.manifest?.digest],['Schema',manifest?.schema_version],['Dataset snapshot',manifest?.dataset_snapshot_id],['Dataset digest',manifest?.dataset_snapshot_digest],['Taxonomy digest',manifest?.taxonomy_digest],['Input catalog digest',manifest?.input_catalog_digest],['Case IDs',identityList(manifest?.case_ids)],['Metric IDs',identityList(manifest?.metric_ids)],['Confidence',manifest?.confidence_policy?JSON.stringify(manifest.confidence_policy):'不可用']]));for(const subject of manifest?.subjects||[]){section.append(el('h3',`${subject.subject} Subject`),definitionList([['Ingestion plan digest',subject.ingestion_plan_digest],['Query plan digest',subject.query_plan_digest],['Ingestion plan',JSON.stringify(subject.ingestion_plan)],['Query plan',JSON.stringify(subject.query_plan)],['Declared identities',identityList((subject.declared_identities||[]).map(item=>`${item.plugin_id} / ${item.implementation_digest}${item.configuration_digest?` / ${item.configuration_digest}`:''}${item.provider_id?` / ${item.provider_id}`:''}${item.model?` / ${item.model}`:''}${item.prompt_digest?` / ${item.prompt_digest}`:''}`))],['Bindings',identityList((subject.bindings||[]).map(item=>`${item.role}:${item.artifact_id} / ${item.artifact_type} / ${item.content_digest}${item.case_id?` / ${item.case_id}`:''}`))]]))}const runtime=manifest?.runtime;section.append(el('h3','Runtime identity'),definitionList([['Runtime digest',runtime?.runtime_digest],['Package digest',runtime?.package_digest],['Implementation digest',runtime?.implementation_digest],['OS family',runtime?.os_family],['Architecture',runtime?.architecture],['Resource sampler',runtime?.resource_sampler_version]]));return section};
 const render=async id=>{status.textContent='正在读取 Evaluation Run…';try{const x=await api(`/api/workbench/evaluation-runs/${id}`),manifest=x.manifest?.value,report=x.report?.value,navigation=x.navigation?.value,header=el('header','',{class:'evaluation-run-header'}),identity=el('div');identity.append(el('h1','Evaluation Run'),statusTag(statusLabel(x.state),statusTone(x.state)),el('code',x.id));header.append(identity,definitionList([['Plan digest',x.planDigest],['创建',formatTime(x.createdAt)],['开始',formatTime(x.startedAt)],['结束',formatTime(x.endedAt)],['Terminal',x.terminalState]]));surface.replaceChildren(header,renderManifest(x,manifest));if((x.unavailable||[]).length)surface.append(notice('failure','Evaluation Artifact 不可用',(x.unavailable||[]).map(u=>`${u.artifactType}: ${u.code}`).join('；')));if(!report){surface.append(emptyState(x.state==='RUNNING'?'评估正在运行':'评估报告不可用',x.state==='RUNNING'?'指标将在不可变报告生成后显示。':'未展示任何合成指标或门禁。'));status.textContent=x.state==='RUNNING'?'Evaluation Run 正在运行。':'Evaluation Report 不可用。';return}
   const workspace=el('section','',{class:'evaluation-run-workspace'}),metricsPane=el('section','',{class:'evaluation-metric-pane'}),diagnostics=el('aside','',{class:'evaluation-diagnostic-pane'}),filters=el('div','',{class:'evaluation-filters'}),owner=el('select','',{'aria-label':'指标 Owner'}),slice=el('input','',{placeholder:'筛选切片值','aria-label':'筛选切片值'});owner.append(el('option','全部 Owner',{value:''}),...owners.filter(x=>!['latency','resources'].includes(x)).map(x=>el('option',ownerLabels[x],{value:x})));filters.append(owner,slice);metricsPane.append(filters);const renderBands=()=>{metricsPane.querySelectorAll('.owner-band').forEach(x=>x.remove());const needle=slice.value.trim().toLowerCase();for(const name of owners){const band=el('section','',{class:'owner-band','data-owner':name}),rows=(x.metrics||[]).filter(m=>m.owner===name&&(!owner.value||m.owner===owner.value)&&(!needle||Object.values(m.slices||{}).some(v=>String(v).toLowerCase().includes(needle))));band.append(sectionHeader(`owner-${name}`,ownerLabels[name],`${rows.length} 个报告`));if(name==='latency'){const operation=report.operation;band.append(operation?definitionList([['Elapsed ms',operation.elapsed_ms],['Availability',operation.availability]]):emptyState('无报告','OperationReport 未返回 latency 事实。'))}else if(name==='resources'){const operation=report.operation;band.append(operation?definitionList([['CPU ms',operation.cpu_ms],['Peak RSS',operation.peak_rss],['IO bytes',operation.io_bytes],['Availability',operation.availability]]):emptyState('无报告','OperationReport 未返回 resource 事实。'))}else if(rows.length){band.append(denseTable(['指标','状态','值','方法 / 方向','阶段','样本','切片'],rows.map(m=>[m.metricId||m.artifactId,statusTag(m.status,statusTone(m.status)),m.value??'不可用',`${m.method||'不可用'} / ${m.direction||'不可用'}`,m.stageKind||'不可用',`${m.matchedCount??0}/${m.labelledCount??0}${m.sampleCount==null?'':` / ${m.sampleCount}`}`,Object.entries(m.slices||{}).map(([k,v])=>`${k}:${v}`).join(' · ')||'不可用']),'分层指标'))}else band.append(emptyState('无报告','当前层没有匹配的 MetricReport。'));metricsPane.append(band)}};owner.addEventListener('change',renderBands);slice.addEventListener('input',renderBands);renderBands();
   diagnostics.append(sectionHeader('gate-title','质量门禁与适用性','永久显示'));const results=new Map((report.gate_results||[]).map(g=>[g.gate_id,g])),configured=manifest?.gates||[];if(configured.length)diagnostics.append(...configured.map(g=>{const result=results.get(g.gate_id),row=el('article','',{class:'gate-row'}),predicate=g.aggregation==='any_failure'?g.failure_code:`${g.direction} ${g.threshold}`;row.append(statusTag(result?.state||'未评估',statusTone(result?.state)),el('strong',g.gate_id||'Gate'),definitionList([['Metric',g.metric_id],['Owner',g.owner],['Selector',JSON.stringify(g.selector)],['Aggregation',g.aggregation],['Predicate / threshold',predicate],['Minimum samples',g.minimum_samples],['Severity',g.severity],['Subject',result?.subject],['Reason',result?.reason],['Samples',result?.sample_count],['Value',result?.value],['State counts',result?.state_counts?JSON.stringify(result.state_counts):'不可用']]));return row}));else if((report.gate_results||[]).length)diagnostics.append(...report.gate_results.map(g=>{const row=el('article','',{class:'gate-row'});row.append(statusTag(g.state,statusTone(g.state)),el('strong',g.gate_id||'Gate'),definitionList([['Configured gate','不可用'],['Subject',g.subject],['Reason',g.reason],['Samples',g.sample_count],['Value',g.value],['State counts',g.state_counts?JSON.stringify(g.state_counts):'不可用']]));return row}));else diagnostics.append(emptyState('没有门禁','Manifest 未配置 Gate，报告也未返回 GateResult。'));const judge=(x.metrics||[]).filter(m=>m.owner==='judge'||m.status==='NOT_APPLICABLE'||m.status==='INSUFFICIENT_LABELS');diagnostics.append(el('h3','Applicability / Judge'),judge.length?definitionList(judge.flatMap(m=>[[m.metricId||m.artifactId,`${m.status}${m.eligibility?` / ${m.eligibility}`:''}`],[`${m.metricId||m.artifactId} calibration Artifact`,m.calibrationReportArtifactId]])):emptyState('没有适用性例外','未返回 Judge 或缺失数据状态。'));
   const links=navigation?.links||report.failed_cases||[],failed=el('section','',{class:'failed-cases'}),chain=el('section','',{class:'evidence-chain'});failed.append(el('h3','失败案例'));const selectLink=(link,updateRoute=true)=>{const caseId=link.case_id||link.caseId;[...failed.querySelectorAll('button')].forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.case===String(caseId))));chain.replaceChildren(el('h3','证据链'),definitionList([['Run',link.evaluation_run_id||x.id],['Gate',link.gate_id],['Metric report',link.metric_report_id],['Metric aggregate',link.metric_aggregate_id],['Ingestion',link.ingestion_artifact_id],['Retrieval',link.retrieval_artifact_id],['Fusion',link.fusion_artifact_id],['Rerank',link.rerank_artifact_id],['Evidence',link.evidence_artifact_id],['Generation',link.generation_artifact_id],['Verification',link.verification_artifact_id],['Final response',link.final_response_artifact_id],['Source',link.source_artifact_id]]));const commands=el('div','',{class:'evidence-chain-actions'});for(const [label,key] of [['Metric','metric_report_id'],['Ingestion','ingestion_artifact_id'],['Retrieval','retrieval_artifact_id'],['Fusion','fusion_artifact_id'],['Rerank','rerank_artifact_id'],['Evidence','evidence_artifact_id'],['Generation','generation_artifact_id'],['Verification','verification_artifact_id'],['Final','final_response_artifact_id'],['Source','source_artifact_id']])if(link[key])commands.append(artifactButton(label,link[key],key==='source_artifact_id'?link.source_locator:null));commands.append(el('span','Query Run 不可用',{class:'muted'}));chain.append(commands);if(updateRoute)history.replaceState(null,'',diagnosisHref('evaluation-run',{run:x.id,q:caseId}))};for(const link of links){const b=button('',()=>selectLink(link));b.className='failed-case-row';b.dataset.case=link.case_id||link.caseId;b.append(el('strong',link.case_id||link.caseId||'case'),el('span',link.subject||'不可用'),el('span',link.gate_id||'不可用'));failed.append(b)}const requestedLink=requestedCase?links.find(link=>(link.case_id||link.caseId)===requestedCase):null;if(!links.length)failed.append(emptyState('没有失败案例','报告未返回失败案例导航。'));else if(requestedCase&&!requestedLink){failed.append(notice('failure','请求案例未找到',`${requestedCase} 不属于此 Evaluation Run 的失败案例。`));chain.replaceChildren(emptyState('证据链不可用','请选择此 Run 中存在的失败案例。'))}else selectLink(requestedLink||links[0],false);diagnostics.append(failed,chain);workspace.append(metricsPane,diagnostics);surface.append(workspace);status.textContent=requestedCase&&!requestedLink?`Evaluation Run ${statusLabel(x.state)}；请求案例未找到。`:`Evaluation Run ${statusLabel(x.state)}，报告已验证。`}catch{surface.replaceChildren(notice('failure','Evaluation Run 不可用','无法读取或验证该运行。'));status.textContent='Evaluation Run 读取失败。'}};
 pick.addEventListener('change',()=>pick.value&&render(pick.value));main.append(heading('评估运行','分层指标、门禁、适用性与失败案例证据'),pick,status,surface);shell(main);api('/api/workbench/evaluation-runs').then(rows=>{pick.append(el('option','选择 Evaluation Run',{value:''}));rows.forEach(row=>pick.append(el('option',`${row.state} / ${row.id}`,{value:row.id})));const id=new URL(location).searchParams.get('run');if(id&&rows.some(row=>row.id===id)){pick.value=id;render(id)}else status.textContent=rows.length?'选择 Evaluation Run。':'没有 Evaluation Run。'}).catch(()=>{status.textContent='评估运行目录不可用。';status.setAttribute('role','alert')})}
function runs(){
 const main=el('main','',{class:'ingestion-page'}),lookup=el('section','',{class:'run-lookup'}),input=el('input','',{placeholder:'Ingestion Run UUID','aria-label':'Ingestion Run UUID'}),panel=el('section','',{class:'ingestion-run-surface','aria-live':'polite'}),query=new URL(location).searchParams.get('run');input.value=query||'';
 const initialStage=stages=>stages.find(stage=>stage.state==='FAILED')||stages.find(stage=>['RUNNING','RETRYING'].includes(stage.state))||stages.at(-1);
 const renderStage=(stage,inspectorPane,artifactActions)=>{const duration=stage.startedAt&&stage.endedAt?`${Math.max(0,new Date(stage.endedAt)-new Date(stage.startedAt))} ms`:'不可用',artifacts=el('section','',{class:'stage-artifacts'}),quality=el('section','',{class:'stage-quality'});artifacts.append(el('h3','输入与输出'));for(const value of stage.inputs||[])artifacts.append(el('div',`${value.artifactType||'Artifact'} / ${value.id||'不可用'}`,{class:'artifact-reference'}));for(const output of stage.outputs||[]){if(artifactActions){const action=button(`Artifact ${output.artifactType}`,event=>inspector(output.id,event.currentTarget));action.className='artifact-action';artifacts.append(action)}else artifacts.append(el('div',`${output.artifactType} / ${output.id}`,{class:'artifact-reference'}))}if(!(stage.inputs||[]).length&&!(stage.outputs||[]).length)artifacts.append(el('p','未返回 Artifact 引用。',{class:'muted'}));quality.append(el('h3','指标与质量'),definitionRows([['Metrics',signalValue(stage.metrics)],['Quality',signalValue(stage.quality)]],'stage-signal-grid'));const header=el('header','',{class:'stage-inspector-header'});header.append(el('h2',stage.stageKey),statusTag(statusLabel(stage.state),statusTone(stage.state)));const failure=stage.failure?notice('failure',stage.failure.code||'阶段失败',stage.failure.message||stage.failure.safeMessage||stage.failure.safe_message||'未返回更多安全失败详情。'):null;inspectorPane.replaceChildren(header,definitionRows([['Plugin',stage.pluginId],['尝试',stage.attempt],['状态',stage.state],['结果',stage.result],['选择',stage.selection],['开始',stage.startedAt],['结束',stage.endedAt],['耗时',duration]],'stage-facts'),artifacts,quality);if(failure)inspectorPane.append(failure)};
 const load=async()=>{if(!input.value)return;panel.replaceChildren(skeletonRows(5));try{const x=await api(`/api/workbench/ingestion-runs/${input.value}`),stages=x.stages||[],resolution=x.resolution||{},article=el('article','',{class:'ingestion-run','data-run-state':x.state}),head=el('header','',{class:'ingestion-run-header'}),copy=el('div'),actions=el('div','',{class:'run-actions'});copy.append(el('span','INGESTION RUN',{class:'eyebrow'}),el('h1','Ingestion Run'),el('code',x.id,{class:'run-identity'}),statusTag(statusLabel(x.state),statusTone(x.state)));if(x.actions?.stop){const stop=button('停止',()=>api(`/api/workbench/ingestion-runs/${x.id}/stop`,{method:'POST'}).then(load));stop.className='command-link';actions.append(stop)}if(x.actions?.rerun){const rerun=button('重新运行',()=>{rerun.remove();const profile=el('input','',{placeholder:'Ingestion Profile Set ID','aria-label':'重新运行 Profile Set ID',maxlength:'64'}),confirm=button('确认重新运行',async()=>{const workspaceProfileId=profile.value.trim();if(!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(workspaceProfileId))return;confirm.disabled=true;try{const p=await api(`/api/workbench/ingestion-runs/${x.id}/rerun-preflight`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({workspaceProfileId})});sessionStorage.setItem('kb2.rerun-preflight',JSON.stringify(p));location.href=href('documents')}catch{confirm.disabled=false}});confirm.className='command-link command-primary';actions.append(profile,confirm);profile.focus()});rerun.className='command-link command-primary';actions.append(rerun)}head.append(copy,definitionRows([['计划摘要',x.planDigest],['开始',x.startedAt],['结束',x.endedAt]],'run-summary'),actions);const rail=el('div','',{class:'ingestion-stage-rail',role:'list','aria-label':'Ingestion 阶段'}),detail=el('div','',{class:'ingestion-detail-grid'}),plan=el('section','',{class:'run-plan-pane'}),stageInspector=el('aside','',{class:'stage-inspector','aria-live':'polite'}),tabs=el('div','',{class:'run-tabs',role:'tablist','aria-label':'Run 信息'}),tabBody=el('div','',{class:'run-tab-panel',role:'tabpanel'});const panels={resolution:()=>definitionRows([['选中 Profile',resolution.selectedProfileId??resolution.selected_profile_id],['选择层级',resolution.selectionTier??resolution.selection_tier],['Observables',resolution.observables],['候选 Profile',resolution.candidateProfileIds??resolution.candidate_profile_ids],['规则评估',resolution.evaluatedRules??resolution.evaluated_rules]],'run-definition-grid'),quality:()=>definitionRows([['Metrics',signalValue(x.metrics)],['Quality',signalValue(x.quality)]],'run-definition-grid'),identity:()=>definitionRows([['Run ID',x.id],['不可变计划摘要',x.planDigest],['状态',x.state]],'run-definition-grid')};const selectTab=name=>{[...tabs.children].forEach(control=>control.setAttribute('aria-selected',String(control.dataset.tab===name)));tabBody.replaceChildren(panels[name]())};for(const [name,label] of [['resolution','Profile 解析'],['quality','Run 指标'],['identity','不可变身份']]){const control=button(label,()=>selectTab(name));control.dataset.tab=name;control.setAttribute('role','tab');tabs.append(control)}selectTab('resolution');plan.append(tabs,tabBody);const selectStage=(stage,control)=>{rail.querySelectorAll('.stage-card').forEach(card=>card.setAttribute('aria-pressed',String(card===control)));renderStage(stage,stageInspector,Boolean(x.actions?.artifact))};let initialControl=null;stages.forEach((stage,index)=>{const item=el('div','',{class:'stage-node',role:'listitem'}),card=button('',()=>selectStage(stage,card));card.className=`stage-card stage-${statusTone(stage.state)}`;card.setAttribute('aria-pressed','false');card.append(el('strong',`${stage.stageKey} #${stage.attempt}`),statusTag(statusLabel(stage.state),statusTone(stage.state)),el('small',stage.selection||stage.result||'等待结果'));item.append(card);if(index<stages.length-1)item.append(el('span','',{class:'stage-connector','aria-hidden':'true'}));rail.append(item);if(stage===initialStage(stages))initialControl=card});detail.append(plan,stageInspector);article.append(head,rail,detail);panel.replaceChildren(article);if(initialControl)initialControl.click()}catch{panel.replaceChildren(notice('failure','Ingestion Run 不可用','请检查 Run ID 后重试。'))}};
 if(query){main.append(panel);shell(main);load()}else{lookup.append(input,button('检查',load));main.append(heading('运行记录','检查一个 Ingestion Run 的固定计划与阶段'),lookup,panel);shell(main)}
}
function comparisonView(){
 const requestedComparison=new URL(location).searchParams.get('comparison'),main=el('main','',{class:'comparison-page'}),base=el('select','',{'aria-label':'基准 Evaluation Report'}),candidate=el('select','',{'aria-label':'候选 Evaluation Report'}),out=el('section','',{class:'comparison-surface','aria-live':'polite'}),controls=el('section','',{class:'comparison-controls','aria-label':'固定比较选择'});let catalog=[],version=0,creating=false;
 const label=(text,control)=>{const node=el('label','',{class:'field-label'});node.append(el('span',text),control);return node};
 const identity=(reports,x)=>{const section=el('section','',{class:'comparison-identity','aria-labelledby':'comparison-identity-title'});section.append(sectionHeader('comparison-identity-title','固定身份','Digest 已验证'));for(const side of ['baseline','candidate']){const r=reports?.[side]||{},m=r.manifest||{},box=el('div','',{class:'identity-side'});box.append(el('h3',side==='baseline'?'基准':'候选'),definitionRows([['Report',r.reportId||x[`${side}_report_id`]],['Run',r.runId],['Manifest digest',m.digest],['Dataset digest',m.datasetDigest],['Taxonomy',m.taxonomyDigest],['Input catalog',m.inputCatalogDigest],['Manifest',m.artifactId],['Dataset',m.datasetSnapshotId],['Cases',m.caseCount],['Metrics',m.metricCount]]));section.append(box)}return section};
 const tableBand=(id,title,headers,rows)=>{const section=el('section','',{class:'comparison-band','aria-labelledby':id});section.append(sectionHeader(id,title,`${rows.length} 条`),denseTable(headers,rows,title));return section};
 const show=d=>{const x=d?.comparison;if(!x){out.replaceChildren(notice('failure','比较 Artifact 不可用',d?.unavailable?.code||'COMPARISON_ARTIFACT_UNAVAILABLE'));return}const axis=el('section','',{class:`comparison-axis ${x.mode==='SINGLE_AXIS'?'ready':'warning'}`});axis.append(el('strong',x.mode),el('span',x.mode==='SINGLE_AXIS'?`唯一变化：${x.axis}`:`非因果比较；变化：${(x.changes||[]).join('、')}`));const quality=(x.quality?.pairs||[]).map(row=>{const b=row.baseline||{},c=row.candidate||{},delta=row.delta||{},context=row.case_id||Object.entries(row.slices||{}).map(([a,v])=>`${a}:${v}`).join(' / ')||'不可用';return [row.owner,row.metric_id,context,b.subject||'不可用',b.status||'不可用',b.value??'不可用',b.sample_count??'不可用',b.labelled_count??'不可用',b.matched_count??'不可用',c.subject||'不可用',c.status||'不可用',c.value??'不可用',c.sample_count??'不可用',c.labelled_count??'不可用',c.matched_count??'不可用',delta.absolute??'不可用',delta.relative??delta.relative_state??'不可用']});
 const confidence=[];for(const side of ['baseline','candidate']){const c=x.confidence?.[side]||{};confidence.push([side,c.state,c.reason||c.method||'不可用',c.level??'不可用',c.numerator??'不可用',c.denominator??'不可用',c.lower??'不可用',c.upper??'不可用'])}const gates=[];for(const side of ['baseline','candidate'])for(const g of x.gates?.[side]||[]){const open=g.aggregate_id?button('Aggregate',e=>inspector(g.aggregate_id,e.currentTarget)):el('span','不可用',{class:'muted'});gates.push([side,g.gate_id,g.subject||'不可用',g.state,g.reason,g.sample_count,g.value??'不可用',Object.entries(g.state_counts||{}).map(([a,b])=>`${a}:${b}`).join(' / ')||'不可用',open])}const cases=[];for(const side of ['baseline','candidate'])for(const item of x.failed_cases?.[side]||[]){const actions=el('div','',{class:'row-actions'});for(const [name,key] of [['Metric','metric_report_id'],['Aggregate','metric_aggregate_id'],['Evidence','evidence_artifact_id'],['Source','source_artifact_id']])if(item[key])actions.append(button(name,e=>inspector(item[key],e.currentTarget)));if(item.evaluation_run_id)actions.append(el('a','案例诊断',{href:diagnosisHref('evaluation-run',{run:item.evaluation_run_id,q:item.case_id,comparison:d.artifactId})}));else actions.append(el('span','案例诊断不可用',{class:'muted'}));cases.push([side,item.case_id,item.gate_id,item.subject,actions])}const latency=[['基准',x.latency?.baseline],['候选',x.latency?.candidate]],resources=['baseline','candidate'].map(side=>{const r=x.resources?.[side]||{};return [side,r.availability,r.cpu_ms??'不可用',r.peak_rss??'不可用',r.io_bytes??'不可用']});const diagnosticGrid=el('div','',{class:'comparison-diagnostic-grid'}),qualityBand=tableBand('comparison-quality-title','质量与变化',['Owner','指标','Case / Slice','基准主体','基准状态','基准值','基准样本','基准标签','基准匹配','候选主体','候选状态','候选值','候选样本','候选标签','候选匹配','绝对变化','相对变化'],quality);qualityBand.classList.add('comparison-quality-band');diagnosticGrid.append(qualityBand,tableBand('comparison-confidence-title','样本与置信区间',['侧','状态','原因 / 方法','置信水平','分子','分母','下界','上界'],confidence),tableBand('comparison-gates-title','质量门禁',['侧','Gate','Subject','状态','原因','样本','值','状态计数','证据'],gates),tableBand('comparison-cases-title','失败案例',['侧','Case','Gate','Subject','诊断'],cases),tableBand('comparison-latency-title','延迟（独立）',['侧','Elapsed ms'],latency),tableBand('comparison-resources-title','本地资源（独立）',['侧','可用性','CPU ms','Peak RSS','I/O bytes'],resources));out.replaceChildren(axis,identity(d.reports,x),diagnosticGrid,el('section',`只读建议：${x.recommendation}`,{class:'comparison-recommendation',role:'note'}))};
 const syncCreate=()=>{const selected=catalog.find(row=>row.reportId===candidate.value);create.disabled=creating||!base.value||!candidate.value||base.value===candidate.value||selected?.compatibility?.state!=='COMPATIBLE'};
 const loadCandidates=async()=>{const current=++version,previous=candidate.value;creating=false;base.disabled=false;candidate.disabled=true;create.disabled=true;out.replaceChildren(skeletonRows(3));try{catalog=await api(`/api/workbench/comparisons/eligible${base.value?`?baselineReportId=${encodeURIComponent(base.value)}`:''}`);if(current!==version)return;candidate.replaceChildren(el('option','选择兼容候选',{value:''}));for(const row of catalog){const c=row.compatibility,state=c?` / ${c.state}${c.reason?` (${c.reason})`:''}`:'';candidate.append(el('option',`${row.reportId} / ${row.manifest.datasetDigest.slice(0,12)}${state}`,{value:row.reportId,disabled:c&&c.state!=='COMPATIBLE'?'true':null}))}if(catalog.some(row=>row.reportId===previous&&row.compatibility?.state==='COMPATIBLE'))candidate.value=previous;out.replaceChildren(emptyState(base.value?'请选择兼容候选':'请选择基准','比较结果由不可变 Artifact 提供。'))}catch{if(current===version)out.replaceChildren(notice('failure','可比较 Evaluation Run 不可用','COMPARISON_CATALOG_UNAVAILABLE',[button('重试',loadCandidates)]))}finally{if(current===version){candidate.disabled=false;syncCreate()}}};
 const candidateChanged=()=>{version++;creating=false;base.disabled=false;candidate.disabled=false;out.replaceChildren(emptyState(candidate.value?'候选已更改':'请选择兼容候选','创建后仅展示当前选择对应的不可变比较。'));syncCreate()};
 const create=button('创建固定比较',async()=>{const current=++version,baselineReportId=base.value,candidateReportId=candidate.value;creating=true;base.disabled=true;candidate.disabled=true;syncCreate();out.replaceChildren(el('div','正在创建不可变比较…',{role:'status'}));try{const r=await api('/api/workbench/comparisons',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({baselineReportId,candidateReportId})});if(current===version)show(r.comparison)}catch(problem){if(current===version)out.replaceChildren(notice('failure','比较不兼容',`${problem.code||'COMPARISON_INCOMPATIBLE'}${problem.reason?` / ${problem.reason}`:''}`))}finally{if(current===version){creating=false;base.disabled=false;candidate.disabled=false;syncCreate()}}},true);controls.append(label('基准 Evaluation Report',base),label('候选 Evaluation Report',candidate),create);main.append(heading('比较','固定实验的质量、门禁、延迟和资源'),controls,out);shell(main);base.addEventListener('change',loadCandidates);candidate.addEventListener('change',candidateChanged);api('/api/workbench/comparisons/eligible').then(rows=>{catalog=rows;base.append(el('option','选择 Evaluation Report',{value:''}));for(const row of rows)base.append(el('option',`${row.reportId} / ${row.manifest.datasetDigest.slice(0,12)}`,{value:row.reportId}));candidate.append(el('option','请先选择基准',{value:''}));if(!requestedComparison)out.replaceChildren(rows.length?emptyState('请选择基准','候选兼容性由服务端验证。'):emptyState('没有可比较报告','完成两个成功 Evaluation Run 后再创建比较。'))}).catch(()=>{if(!requestedComparison)out.replaceChildren(notice('failure','可比较 Evaluation Run 不可用','COMPARISON_CATALOG_UNAVAILABLE',[button('重试',()=>location.reload())]))});if(/^[0-9a-f-]{36}$/i.test(requestedComparison||'')){out.replaceChildren(el('div','正在加载不可变比较…',{role:'status'}));api(`/api/workbench/comparisons/${requestedComparison}`).then(show).catch(problem=>out.replaceChildren(notice('failure','比较 Artifact 不可用',problem.code||'COMPARISON_ARTIFACT_UNAVAILABLE')))} }
function historyView(){
 const raw=new URL(location).searchParams,validType=/^(INGESTION|QUERY|EVALUATION|COMPARISON|CONTRACT_TEST|UNKNOWN)$/,validState=/^(PENDING|RUNNING|SUCCEEDED|FAILED)$/,validRun=/^[0-9a-f]{8}-[0-9a-f-]{27}$/i;const type=el('select','',{'aria-label':'Run 类型'}),state=el('select','',{'aria-label':'Run 状态'}),q=el('input','',{placeholder:'Run、Profile 或 Plugin','aria-label':'筛选 Run',maxlength:'64'}),list=el('section','',{class:'run-table-region','aria-live':'polite'}),detail=el('aside','',{class:'run-detail','aria-live':'polite','aria-label':'Run 诊断'}),filters=el('form','',{class:'run-filters','aria-label':'Run 筛选'}),layout=el('div','',{class:'run-history-workspace'});let listVersion=0,detailVersion=0,actionVersion=0,timer=null,selected=validRun.test(raw.get('run')||'')?raw.get('run'):null,lastDetail=null;
 for(const v of ['','INGESTION','QUERY','EVALUATION','COMPARISON','CONTRACT_TEST','UNKNOWN'])type.append(el('option',v||'全部类型',{value:v}));for(const v of ['','PENDING','RUNNING','SUCCEEDED','FAILED'])state.append(el('option',v||'全部状态',{value:v}));type.value=validType.test(raw.get('runType')||'')?raw.get('runType'):'';state.value=validState.test(raw.get('runState')||'')?raw.get('runState'):'';q.value=(raw.get('q')||'').slice(0,64);
 const updateUrl=(replace=false)=>{const href=diagnosisHref('runs',{run:selected,runType:type.value,runState:state.value,q:q.value}),method=replace?'replaceState':'pushState';history[method](null,'',href)};
 const renderDetail=(x,stale=false,outside=false)=>{lastDetail=x;const head=el('header','',{class:'run-detail-head'}),close=iconButton('close','关闭 Run 诊断',()=>{detailVersion++;actionVersion++;selected=null;lastDetail=null;detail.replaceChildren(emptyState('未选择 Run','从表格激活一条运行记录。'));updateUrl()});head.append(el('div',`${x.type} / ${x.state}`),close);const actions=el('div','',{class:'run-actions'}),actionStatus=el('span','',{class:'action-status','aria-live':'polite'});if(x.actions?.stop){const stop=button('停止',async()=>{const request=++actionVersion;stop.disabled=true;actionStatus.textContent='正在请求停止…';try{await api(`/api/workbench/${x.type==='QUERY'?'query-runs':'ingestion-runs'}/${x.id}/stop`,{method:'POST'});if(request===actionVersion)await show(x.id,true)}catch(problem){if(request===actionVersion){actionStatus.textContent=problem.code||'STOP_UNAVAILABLE';stop.disabled=false}}});actions.append(stop)}if(x.type==='INGESTION'&&x.actions?.rerun){const profile=el('input','',{placeholder:'Ingestion Profile Set ID','aria-label':'重新运行 Profile Set ID',maxlength:'64'}),rerun=button('重新运行',async()=>{const workspaceProfileId=profile.value.trim();if(!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(workspaceProfileId)){actionStatus.textContent='PROFILE_ID_INVALID';return}const request=++actionVersion;rerun.disabled=true;try{const preflight=await api(`/api/workbench/ingestion-runs/${x.id}/rerun-preflight`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({workspaceProfileId})});if(request!==actionVersion)return;sessionStorage.setItem('kb2.rerun-preflight',JSON.stringify(preflight));location.href=diagnosisHref('documents')}catch(problem){if(request===actionVersion){actionStatus.textContent=problem.code||'RERUN_PREFLIGHT_UNAVAILABLE';rerun.disabled=false}}});actions.append(profile,rerun)}actions.append(actionStatus);const identity=definitionRows([['Run',x.id],['状态',x.state],['终态',x.terminalState],['Plan digest',x.planDigest],['Profile',x.profileId],['Plugins',(x.pluginIds||[]).join(' / ')],['Input',`${x.input?.kind||'unavailable'} / ${x.input?.summary||'不可用'}`],['耗时',x.durationMs==null?'不可用':`${x.durationMs} ms`]]);const destinations=el('nav','',{class:'run-destinations','aria-label':'诊断目的地'});for(const d of x.destinations||[]){if(d.kind==='artifact')destinations.append(button(d.label,e=>inspector(d.artifactId,e.currentTarget)));else if(d.kind==='trace')destinations.append(el('a',d.label,{href:diagnosisHref('runs',{run:d.runId})}));else if(d.kind==='route')destinations.append(el('a',d.label,{href:diagnosisHref(d.route,{run:d.runId,comparison:d.comparisonArtifactId})}));else destinations.append(el('span',d.label,{class:'muted'}))}const stages=el('section','',{class:'run-flow','aria-label':'阶段尝试'});for(const s of x.stages||[]){const row=el('article','',{class:'run-stage'}),top=el('div','',{class:'run-stage-head'});top.append(el('strong',`${s.stageKey} #${s.attempt}`),statusTag(s.state,statusTone(s.state)),el('span',s.pluginId||'Plugin 不可用',{class:'muted'}),el('span',s.durationMs==null?'耗时不可用':`${s.durationMs} ms`));row.append(top);if(s.failure)row.append(el('code',s.failure.code,{class:'failure-code'}));for(const a of s.inputs||[])row.append(button(`输入 ${a.artifactType} / ${a.summary||'无摘要'}`,e=>inspector(a.id,e.currentTarget)));for(const a of s.artifacts||[])row.append(button(`输出 ${a.artifactType} / ${a.summary||'无摘要'}`,e=>inspector(a.id,e.currentTarget)));stages.append(row)}const banners=[];if(stale)banners.push(notice('warning','诊断数据可能已过期','保留上次有效详情；可重新选择该 Run。'));if(outside)banners.push(notice('warning','当前筛选范围外','所选 Run 仍保持可诊断。'));detail.replaceChildren(head,...banners,identity,actions,destinations,stages)};
 const show=async(id,replace=false)=>{selected=id;updateUrl(replace);const request=++detailVersion;detail.replaceChildren(el('div','正在加载 Run 诊断…',{role:'status'}));try{const x=await api(`/api/workbench/runs/${id}`);if(request!==detailVersion)return;renderDetail(x,false,false);detail.querySelector('.run-detail-head')?.focus()}catch(problem){if(request!==detailVersion)return;if(lastDetail)renderDetail(lastDetail,true,false);else detail.replaceChildren(notice('failure','Run 诊断不可用',problem.code||'RUN_NOT_FOUND',[button('重试',()=>show(id,true))]))}};
 const refresh=async()=>{const request=++listVersion;list.replaceChildren(skeletonRows(5));try{const rows=await api(`/api/workbench/runs?runType=${type.value}&state=${state.value}&q=${encodeURIComponent(q.value)}`);if(request!==listVersion)return;const tableRows=rows.map(r=>{const activate=button(r.id,()=>show(r.id));activate.className='run-select';if(r.id===selected){activate.setAttribute('aria-pressed','true');activate.setAttribute('aria-current','true')}const trace=button('Trace',()=>show(r.id));trace.className='text-action';return [activate,r.type,r.profileId||(r.pluginIds||[]).join(' / ')||'不可用',`${r.input?.kind||'unavailable'} / ${r.input?.summary||'不可用'}`,statusTag(r.state,statusTone(r.state)),r.durationMs==null?'不可用':`${r.durationMs} ms`,formatTime(r.startedAt),trace]});list.replaceChildren(rows.length?denseTable(['Run','类型','Profile / Plugin','输入','状态','耗时','开始','Trace'],tableRows,'混合 Run 历史'):emptyState(type.value||state.value||q.value?'没有匹配的 Run':'尚无 Run','调整筛选条件或创建新的运行。'));if(selected){const inScope=rows.some(row=>row.id===selected),control=list.querySelector('.run-select[aria-pressed="true"]'),wrap=control?.closest('.table-wrap');if(innerWidth<900&&wrap)wrap.scrollTop=Math.max(0,control.closest('tr').offsetTop-34);if(!lastDetail)show(selected,true);else renderDetail(lastDetail,false,!inScope)}}catch{if(request===listVersion){list.replaceChildren(notice('failure','Run 列表不可用','RUN_HISTORY_UNAVAILABLE',[button('重试',refresh)]));if(lastDetail)renderDetail(lastDetail,true,false)}}};
 const changed=()=>{updateUrl();clearTimeout(timer);timer=setTimeout(refresh,150)};[type,state].forEach(control=>control.addEventListener('change',changed));q.addEventListener('input',changed);filters.addEventListener('submit',event=>event.preventDefault());const clear=button('清除筛选',()=>{type.value='';state.value='';q.value='';changed()});filters.append(type,state,q,clear);layout.append(list,detail);const main=el('main','',{class:'run-history-page'});main.append(heading('运行记录','混合 Run 历史与真实 Trace/Artifact 链接'),filters,layout);shell(main);detail.append(emptyState('未选择 Run','从表格激活一条运行记录。'));addEventListener('popstate',()=>location.reload());refresh()}
const requested=new URL(location).searchParams.get('workspace'),routeId=location.pathname.split('/').filter(Boolean).at(-1),routeQuery=new URL(location).searchParams;workspaceId=/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(requested||'')?requested:null;if(routeId==='query')queryLab();else if(routeId==='evaluation-run')evaluationRun();else if(route()[0]==='overview')overview();else if(route()[0]==='studio')studio();else if(route()[0]==='plugins')plugins();else if(route()[0]==='documents')documents();else if(route()[0]==='evaluation-dataset')evaluationDataset();else if(route()[0]==='compare')comparisonView();else if(route()[0]==='runs'&&routeQuery.get('legacy')==='ingestion')runs();else if(route()[0]==='runs')historyView();else{const m=el('main');m.append(heading(route()[1],'该工作流将在后续交付中提供。'));shell(m)}
