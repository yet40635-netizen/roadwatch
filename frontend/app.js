const $ = (id) => document.getElementById(id);
const L = window.L;
const labels = {oil:"油渍", garbage:"垃圾杂物", water:"积水", obstacle:"障碍物", accident:"事故", pothole:"坑洞", congestion:"拥堵", speed_drop:"异常降速", open:"待确认", acknowledged:"处理中", resolved:"已解决", dismissed:"已排除", demo:"演示", vision:"视觉模型", timeseries:"时序分析", queued:"排队中", running:"执行中", succeeded:"已完成", failed:"失败", high:"高", medium:"中"};
const state = {sources:[], events:[], metrics:[], total:0, offset:0, view:"monitor", dataset:null, image:null, boxes:[], annotationImage:null, inferenceImage:null, inferenceBoxes:[], mapPoints:[], token:sessionStorage.getItem("roadwatch-key") || "", map:null, mapMarkers:{}, ws:null, videoTimer:null, videoStream:null};
const titles = {monitor:"运行总览", inference:"图片检测", video:"视频实时检测", datasets:"数据集与标注", sources:"监测点管理", training:"AI 训练工作流"};
let activeJob = 0;
let eventImageURL = null;
let currentEvent = null;
const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const date = (value) => new Date(value).toLocaleString("zh-CN", {hour12:false});
const nameOf = (id) => state.sources.find((item) => item.id === id)?.name || id;
const badge = (value) => '<span class="badge '+escapeHTML(value)+'">'+escapeHTML(labels[value] || value)+'</span>';
function notify(message, error=false){ $("notice").hidden=false; $("notice").className="notice"+(error?" error":""); $("notice").textContent=message; }
function run(action){ return Promise.resolve().then(action).catch((error)=>notify(error.message,true)); }
async function request(path, options={}){
  const headers = new Headers(options.headers);
  if(state.token) headers.set("X-API-Key",state.token);
  if(options.body && !(options.body instanceof FormData)) headers.set("Content-Type","application/json");
  const response=await fetch(path.startsWith("/api/")?path:"/api/v1"+path,{...options,headers});
  if(!response.ok){
    const body=await response.json().catch(()=>({}));
    throw new Error(body.error?.message || body.detail || "请求失败："+response.status);
  }
  return response;
}
async function api(path,options){ return (await request(path,options)).json(); }
const json = (method,body) => ({method,body:JSON.stringify(body)});
function sourceOptions(id){
  const select=$(id), previous=select.value;
  select.innerHTML=state.sources.map((s)=>'<option value="'+escapeHTML(s.id)+'">'+escapeHTML(s.name)+'</option>').join("");
  if(state.sources.some((s)=>s.id===previous))select.value=previous;
}
async function refresh(){
  const [overview,sources]=await Promise.all([api("/overview"),api("/sources")]);
  state.sources=sources;
  ["metric-source","inference-source","ingest-source"].forEach(sourceOptions);
  $("stat-sources").textContent=overview.sources; $("stat-open").textContent=overview.open_events;
  $("stat-high").textContent=overview.high_events; $("stat-jobs").textContent=overview.queued_jobs;
  $("seed").hidden=!overview.demo_enabled;
  $("last-updated").textContent="更新于 "+new Date().toLocaleTimeString("zh-CN",{hour12:false});
  renderSources();
  await Promise.all([loadEvents(),loadMetrics()]);
}
async function loadEvents(){
  const params=new URLSearchParams({limit:"10",offset:String(state.offset)});
  if($("status-filter").value)params.set("status",$("status-filter").value);
  if($("kind-filter").value)params.set("kind",$("kind-filter").value);
  const data=await api("/events?"+params);
  state.events=data.items;state.total=data.total;
  $("event-count").textContent=data.total;
  $("events-body").innerHTML=data.items.length?data.items.map((e)=>'<tr><td><strong>'+escapeHTML(labels[e.kind])+'</strong></td><td>'+escapeHTML(nameOf(e.source_id))+'</td><td>'+escapeHTML(date(e.created_at))+'</td><td>'+badge(e.severity)+'</td><td>'+badge(e.origin)+'</td><td>'+badge(e.status)+'</td><td><button class="secondary" data-event="'+e.id+'">查看处置</button></td></tr>').join(""):'<tr><td colspan="7" class="empty">暂无事件。可载入演示数据，或接入图片与交通指标。</td></tr>';
  $("page-info").textContent=data.total?(state.offset+1)+"–"+(state.offset+data.items.length)+" / "+data.total:"0 条";
  $("prev").disabled=state.offset===0; $("next").disabled=state.offset+10>=data.total;
  const all=await api("/events?limit=100&status=open");
  const acknowledged=await api("/events?limit=100&status=acknowledged");
  state.activeSources=new Set([...all.items,...acknowledged.items].map((e)=>e.source_id));
  drawMap();
}
async function loadMetrics(){
  const id=$("metric-source").value;
  state.metrics=id?await api("/metrics?source_id="+encodeURIComponent(id)):[];
  drawChart();
}
function canvasContext(id){
  const canvas=$(id), rect=canvas.getBoundingClientRect(), ratio=devicePixelRatio||1;
  if(!rect.width || !rect.height)return null;
  canvas.width=Math.round(rect.width*ratio);canvas.height=Math.round(rect.height*ratio);
  const ctx=canvas.getContext("2d");ctx.scale(ratio,ratio);ctx.font='12px "Segoe UI","Microsoft YaHei",sans-serif';
  return {ctx,w:rect.width,h:rect.height,canvas};
}
function drawMap(){
  const el=$("map");
  if(!state.map){
    state.map=L.map(el,{zoomControl:true,scrollWheelZoom:false}).setView([22.3,114.16],11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{
      attribution:'© OpenStreetMap',maxZoom:19,
    }).addTo(state.map);
  }
  Object.values(state.mapMarkers).forEach(m=>state.map.removeLayer(m));
  state.mapMarkers={};
  if(!state.sources.length)return;
  const bounds=[];
  for(const s of state.sources){
    const active=state.activeSources?.has(s.id);
    const color=active?"#ce785c":"#159477";
    const icon=L.divIcon({
      className:"",
      html:`<div style="width:18px;height:18px;border-radius:50%;background:${color};border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)"></div>`,
      iconSize:[18,18],iconAnchor:[9,9],
    });
    const marker=L.marker([s.latitude,s.longitude],{icon}).addTo(state.map)
      .bindPopup(`<strong>${escapeHTML(s.name)}</strong><br>${s.latitude.toFixed(5)}, ${s.longitude.toFixed(5)}<br>基线 ${s.baseline_speed} km/h`)
      .on("click",()=>{$("metric-source").value=s.id;run(loadMetrics);});
    state.mapMarkers[s.id]=marker;
    bounds.push([s.latitude,s.longitude]);
  }
  if(bounds.length>1)state.map.fitBounds(bounds,{padding:[40,40]});
}
function drawChart(){
  const surface=canvasContext("chart");if(!surface)return;
  const {ctx,w,h}=surface,rows=state.metrics,pad=35;
  ctx.fillStyle="#72868e";
  if(!rows.length){ctx.fillText("该监测点尚无交通指标",24,h/2);return;}
  const max=Math.max(80,...rows.map(r=>Math.max(r.speed,r.baseline)))*1.1;
  for(let i=0;i<4;i++){
    const y=12+(h-48)*i/3;ctx.strokeStyle="#e9eff0";ctx.beginPath();ctx.moveTo(pad,y);ctx.lineTo(w-10,y);ctx.stroke();
    ctx.fillText(Math.round(max*(1-i/3)),0,y+4);
  }
  const x=(i)=>pad+(w-pad-12)*i/Math.max(1,rows.length-1),y=(v)=>12+(h-48)*(1-v/max);
  for(const [key,color,dash] of [["baseline","#9aafb6",[5,5]],["speed","#087f68",[]]]){
    ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=2;ctx.setLineDash(dash);
    rows.forEach((r,i)=>i?ctx.lineTo(x(i),y(r[key])):ctx.moveTo(x(i),y(r[key])));ctx.stroke();
  }
  ctx.setLineDash([]);
  rows.forEach((r,i)=>{if(r.anomaly){ctx.beginPath();ctx.arc(x(i),y(r.speed),4,0,Math.PI*2);ctx.fillStyle="#d27a50";ctx.fill();}});
  ctx.fillStyle="#72868e";ctx.fillText(new Date(rows[0].observed_at).toLocaleTimeString("zh-CN"),pad,h-8);
  ctx.fillText(new Date(rows.at(-1).observed_at).toLocaleTimeString("zh-CN"),Math.max(pad,w-80),h-8);
  $("chart-caption").textContent="最新："+rows.at(-1).speed+" km/h · "+rows.at(-1).reason;
}
async function openEvent(id){
  const [event,actions]=await Promise.all([api("/events/"+id),api("/events/"+id+"/actions")]);
  currentEvent=event;
  $("event-title").textContent=labels[event.kind]+" · "+nameOf(event.source_id);
  $("event-description").textContent=event.description;
  $("event-actions").textContent=actions.length?actions.map(a=>date(a.created_at)+" "+labels[a.status]+" "+a.note).join("\n"):"暂无处置记录";
  $("event-actions").style.whiteSpace="pre-wrap";$("action-note").value="";
  const statuses=event.status==="open"?["acknowledged","dismissed"]:event.status==="acknowledged"?["resolved","dismissed"]:[];
  $("event-buttons").innerHTML=statuses.map(s=>'<button data-action="'+s+'">'+labels[s]+'</button>').join("");
  $("event-image").replaceChildren();
  if(eventImageURL)URL.revokeObjectURL(eventImageURL);
  if(event.image_id){
    const blob=await (await request("/images/"+event.image_id+"/content")).blob();
    eventImageURL=URL.createObjectURL(blob);const image=new Image();image.src=eventImageURL;image.alt="事件原始图片";$("event-image").append(image);
  }
  // AI analysis
  const aiSection=$("ai-analysis-section");
  if(event.ai_analysis){
    aiSection.style.display="block";
    $("ai-analysis-content").textContent=event.ai_analysis;
  }else{
    aiSection.style.display="none";
  }
  if(!$("event-dialog").open)$("event-dialog").showModal();
}
async function loadImage(id){
  const blob=await (await request("/images/"+id+"/content")).blob();
  const url=URL.createObjectURL(blob),image=new Image();
  try{image.src=url;await image.decode();return image;}finally{URL.revokeObjectURL(url);}
}
function drawImage(id,image,boxes=[]){
  const surface=canvasContext(id);if(!surface)return null;
  const {ctx,w,h}=surface;ctx.fillStyle="#f3f6f7";ctx.fillRect(0,0,w,h);
  if(!image){ctx.fillStyle="#7c8f96";ctx.fillText("选择图片后显示",20,h/2);return null;}
  const scale=Math.min(w/image.width,h/image.height),iw=image.width*scale,ih=image.height*scale,left=(w-iw)/2,top=(h-ih)/2;
  ctx.drawImage(image,left,top,iw,ih);ctx.strokeStyle="#f6bc48";ctx.lineWidth=2;
  for(const box of boxes){
    ctx.strokeRect(left+box.x*iw,top+box.y*ih,box.width*iw,box.height*ih);
    const text=(labels[box.label]||box.label)+(box.confidence!=null?" "+Math.round(box.confidence*100)+"%":"");
    const bx=left+box.x*iw,by=top+box.y*ih;ctx.fillStyle="#193c44";ctx.fillRect(bx,Math.max(top,by-20),ctx.measureText(text).width+12,20);
    ctx.fillStyle="#fff";ctx.fillText(text,bx+6,Math.max(top,by-20)+14);
  }
  return {left,top,iw,ih};
}
async function showJob(id){
  const serial=++activeJob;
  for(let i=0;i<120;i++){
    const job=await api("/inference/jobs/"+id);if(serial!==activeJob)return;
    $("job-status").textContent="任务 "+job.id.slice(0,8)+" · "+labels[job.status];
    if(job.status==="failed")throw new Error(job.error||"检测失败");
    if(job.status==="succeeded"){
      state.inferenceImage=await loadImage(job.image_id);state.inferenceBoxes=job.result.detections;
      $("inference-mode").textContent=job.result.mode==="demo"?"演示模式":"真实模型";
      $("job-status").textContent=job.result.warning||"检测完成 · 推理耗时 "+job.result.latency_ms+" ms";
      drawImage("inference-canvas",state.inferenceImage,state.inferenceBoxes);
      $("detections").textContent=job.result.detections.length?job.result.detections.map(d=>labels[d.label]+" "+Math.round(d.confidence*100)+"%").join(" · "):"未检测到目标";
      await loadJobs();return;
    }
    await new Promise(resolve=>setTimeout(resolve,1000));
  }
  $("job-status").textContent="任务仍在执行，可稍后在最近任务中查看。";
}
async function loadJobs(){
  const jobs=await api("/inference/jobs");
  $("jobs-list").innerHTML=jobs.length?jobs.map(j=>'<button class="list-item" data-job="'+j.id+'">'+escapeHTML(nameOf(j.source_id))+' · '+labels[j.status]+'<small>'+escapeHTML(date(j.created_at))+' / '+j.id.slice(0,8)+'</small></button>').join(""):'<p class="empty">暂无检测任务</p>';
}
async function loadDatasets(){
  const datasets=await api("/datasets");
  $("datasets-list").innerHTML=datasets.length?datasets.map(d=>'<button class="list-item '+(state.dataset?.id===d.id?"selected":"")+'" data-dataset="'+d.id+'">'+escapeHTML(d.name)+'<small>'+escapeHTML(d.description||"暂无描述")+'</small></button>').join(""):'<p class="empty">创建首个数据集开始标注</p>';
  state.datasets=datasets;
}
async function selectDataset(id){
  state.dataset=state.datasets.find(d=>d.id===id);
  state.image=null;state.annotationImage=null;state.boxes=[];$("save-annotations").disabled=true;
  $("dataset-title").textContent=state.dataset.name;$("upload-dataset-button").disabled=false;$("export-dataset").disabled=false;
  await Promise.all([loadDatasets(),loadDatasetImages()]);
  drawImage("annotation-canvas",null);$("annotation-count").textContent="请选择图片。";
}
async function loadDatasetImages(){
  const images=await api("/datasets/"+state.dataset.id+"/images?limit=500");
  state.images=images;
  $("images-list").innerHTML=images.length?images.map(i=>'<button class="secondary" data-image="'+i.id+'">'+escapeHTML(i.filename)+' · '+i.annotations.length+' 框</button>').join(""):'<p class="empty">该数据集暂无图片</p>';
}
async function selectImage(id){
  state.image=state.images.find(i=>i.id===id);state.boxes=structuredClone(state.image.annotations);
  state.annotationImage=await loadImage(id);$("annotation-split").value=state.image.split;$("save-annotations").disabled=false;
  drawAnnotation();
}
function drawAnnotation(){state.annotationGeometry=drawImage("annotation-canvas",state.annotationImage,state.boxes);$("annotation-count").textContent=state.image?state.image.filename+" · "+state.boxes.length+" 个标注框":"请选择图片";}
function renderSources(){
  $("sources-list").innerHTML=state.sources.length?state.sources.map(s=>'<div class="list-item">'+escapeHTML(s.name)+'<small>'+s.latitude.toFixed(5)+', '+s.longitude.toFixed(5)+' · 基线 '+s.baseline_speed+' km/h</small><small>'+s.id+'</small></div>').join(""):'<p class="empty">暂无监测点</p>';
}
async function changeView(view){
  state.view=view;document.querySelectorAll(".view").forEach(s=>s.hidden=s.id!=="view-"+view);
  document.querySelectorAll("[data-view]").forEach(b=>b.classList.toggle("active",b.dataset.view===view));
  $("page-title").textContent=titles[view];
  if(view==="monitor"){await refresh();}
  if(view==="inference"){drawImage("inference-canvas",state.inferenceImage,state.inferenceBoxes);await loadJobs();}
  if(view==="video"){initVideo();}
  if(view==="datasets"){await loadDatasets();drawAnnotation();}
}
document.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>run(()=>changeView(b.dataset.view)));
$("api-key").value=state.token;
$("auth-form").onsubmit=e=>{e.preventDefault();state.token=$("api-key").value.trim();sessionStorage.setItem("roadwatch-key",state.token);run(async()=>{await refresh();notify("连接成功。");});};
$("refresh").onclick=()=>run(async()=>{await refresh();if(state.view==="inference")await loadJobs();if(state.view==="datasets")await loadDatasets();});
$("seed").onclick=()=>run(async()=>{await api("/demo/seed",{method:"POST"});state.offset=0;await refresh();notify("已载入演示数据。演示事件不代表真实道路情况。");});
$("metric-source").onchange=()=>run(loadMetrics);
for(const id of ["status-filter","kind-filter"])$(id).onchange=()=>{state.offset=0;run(loadEvents);};
$("prev").onclick=()=>{state.offset=Math.max(0,state.offset-10);run(loadEvents);};
$("next").onclick=()=>{state.offset+=10;run(loadEvents);};
$("events-body").onclick=e=>{const button=e.target.closest("[data-event]");if(button)run(()=>openEvent(button.dataset.event));};
$("ai-regenerate").onclick=()=>run(async()=>{
  if(!currentEvent)return;
  notify("正在请求 AI 分析...");
  try{await api("/events/"+currentEvent.id+"/ai-analysis",{method:"POST"});await openEvent(currentEvent.id);notify("AI 分析已更新。");}
  catch(e){notify("AI 分析请求失败:"+e.message);}
});
$("event-buttons").onclick=e=>{const button=e.target.closest("[data-action]");if(button)run(async()=>{
  button.disabled=true;
  try{await api("/events/"+currentEvent.id,json("PATCH",{status:button.dataset.action,note:$("action-note").value}));await openEvent(currentEvent.id);await refresh();}
  finally{button.disabled=false;}
});};
$("inference-form").onsubmit=e=>{e.preventDefault();run(async()=>{
  const data=new FormData();data.append("source_id",$("inference-source").value);data.append("file",$("inference-file").files[0]);
  const job=await api("/inference/jobs",{method:"POST",body:data});await loadJobs();await showJob(job.id);
});};
$("jobs-list").onclick=e=>{const b=e.target.closest("[data-job]");if(b)run(()=>showJob(b.dataset.job));};
$("dataset-form").onsubmit=e=>{e.preventDefault();run(async()=>{
  const row=await api("/datasets",json("POST",{name:$("dataset-name").value,description:$("dataset-description").value}));
  $("dataset-form").reset();await loadDatasets();await selectDataset(row.id);
});};
$("datasets-list").onclick=e=>{const b=e.target.closest("[data-dataset]");if(b)run(()=>selectDataset(b.dataset.dataset));};
$("dataset-upload").onsubmit=e=>{e.preventDefault();run(async()=>{
  if(!state.dataset)throw new Error("请先选择数据集");
  const data=new FormData();data.append("file",$("dataset-file").files[0]);
  const image=await api("/datasets/"+state.dataset.id+"/images",{method:"POST",body:data});
  await loadDatasetImages();await selectImage(image.id);$("dataset-upload").reset();
});};
$("images-list").onclick=e=>{const b=e.target.closest("[data-image]");if(b)run(()=>selectImage(b.dataset.image));};
$("save-annotations").onclick=()=>run(async()=>{
  if(!state.image)return;
  await api("/images/"+state.image.id+"/annotations",json("PUT",{split:$("annotation-split").value,annotations:state.boxes}));
  await loadDatasetImages();notify("标注已保存。");
});
$("undo-box").onclick=()=>{state.boxes.pop();drawAnnotation();};
$("export-dataset").onclick=()=>run(async()=>{
  const blob=await(await request("/datasets/"+state.dataset.id+"/export")).blob(),url=URL.createObjectURL(blob);
  const anchor=document.createElement("a");anchor.href=url;anchor.download="roadwatch-dataset.zip";anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
let drag=null;
function annotationPoint(event){
  const g=state.annotationGeometry;if(!g)return null;
  const r=$("annotation-canvas").getBoundingClientRect();
  return {x:Math.max(0,Math.min(1,(event.clientX-r.left-g.left)/g.iw)),y:Math.max(0,Math.min(1,(event.clientY-r.top-g.top)/g.ih))};
}
$("annotation-canvas").onpointerdown=e=>{if(!state.image)return;drag=annotationPoint(e);$("annotation-canvas").setPointerCapture(e.pointerId);};
$("annotation-canvas").onpointerup=e=>{
  if(!drag)return;const end=annotationPoint(e);
  if(end){const box={label:$("annotation-label").value,x:Math.min(drag.x,end.x),y:Math.min(drag.y,end.y),width:Math.abs(end.x-drag.x),height:Math.abs(end.y-drag.y)};
    if(box.width>.003&&box.height>.003)state.boxes.push(box);}
  drag=null;drawAnnotation();
};
$("annotation-canvas").onpointercancel=()=>{drag=null;};
$("source-form").onsubmit=e=>{e.preventDefault();run(async()=>{
  const form=new FormData(e.target);await api("/sources",json("POST",{name:form.get("name"),latitude:Number(form.get("latitude")),longitude:Number(form.get("longitude")),baseline_speed:Number(form.get("baseline_speed"))}));
  e.target.reset();await refresh();notify("监测点已创建。");
});};
$("metric-form").onsubmit=e=>{e.preventDefault();run(async()=>{
  const form=new FormData(e.target),result=await api("/metrics",json("POST",{source_id:$("ingest-source").value,observed_at:new Date().toISOString(),speed:Number(form.get("speed")),congestion:Number(form.get("congestion")),volume:Number(form.get("volume"))}));
  $("metric-result").textContent=(result.anomaly?"已识别异常：":"指标正常：")+result.reason;await refresh();
});};
function initVideo(){
  if(state.videoInitialized)return;
  state.videoInitialized=true;
  const type=$("video-source-type"),fileLabel=$("video-file-label"),file=$("video-file");
  type.onchange=()=>{fileLabel.hidden=type.value!=="file";file.required=type.value==="file";};
  $("video-start").onclick=()=>run(startVideo);
  $("video-stop").onclick=stopVideo;
}
async function startVideo(){
  const video=$("video-player"),canvas=$("video-canvas");
  if($("video-source-type").value==="camera"){
    state.videoStream=await navigator.mediaDevices.getUserMedia({video:true});
    video.srcObject=state.videoStream;
  }else{
    const f=$("video-file").files[0];
    if(!f)throw new Error("请选择视频文件");
    video.src=URL.createObjectURL(f);
  }
  video.hidden=false;canvas.hidden=false;
  await video.play();
  $("video-start").hidden=true;$("video-stop").hidden=false;
  $("video-status").textContent="检测中…";
  const interval=Math.max(100,parseFloat($("video-interval").value)*1000);
  state.videoTimer=setInterval(()=>run(captureAndDetect),interval);
}
function stopVideo(){
  if(state.videoTimer){clearInterval(state.videoTimer);state.videoTimer=null;}
  if(state.videoStream){state.videoStream.getTracks().forEach(t=>t.stop());state.videoStream=null;}
  const video=$("video-player");video.pause();video.src="";video.srcObject=null;
  $("video-start").hidden=false;$("video-stop").hidden=true;
  $("video-status").textContent="已停止。";
}
async function captureAndDetect(){
  const video=$("video-player"),canvas=$("video-canvas");
  if(video.paused||video.ended)return;
  canvas.width=video.videoWidth;canvas.height=video.videoHeight;
  const ctx=canvas.getContext("2d");
  ctx.drawImage(video,0,0);
  try{
    const blob=await new Promise(r=>canvas.toBlob(r,"image/jpeg",0.8));
    const form=new FormData();form.append("file",blob,"frame.jpg");
    const data=await (await request("/../inference/predict",{method:"POST",body:form})).json();
    $("video-mode").textContent=data.mode==="demo"?"演示模式":"真实模型";
    ctx.strokeStyle="#f6bc48";ctx.lineWidth=3;ctx.fillStyle="#193c44";
    for(const d of data.detections){
      const x=d.x*canvas.width,y=d.y*canvas.height,w=d.width*canvas.width,h=d.height*canvas.height;
      ctx.strokeRect(x,y,w,h);
      const text=(labels[d.label]||d.label)+" "+Math.round(d.confidence*100)+"%";
      ctx.fillRect(x,Math.max(0,y-22),ctx.measureText(text).width+12,22);
      ctx.fillStyle="#fff";ctx.fillText(text,x+6,Math.max(16,y-6));ctx.fillStyle="#193c44";
    }
    $("video-detections").textContent=data.detections.length?data.detections.map(d=>labels[d.label]+" "+Math.round(d.confidence*100)+"%").join(" · "):"未检测到目标";
    $("video-status").textContent="推理 "+data.latency_ms+" ms";
  }catch(e){$("video-status").textContent="检测出错："+e.message;}
}
function connectWS(){
  const proto=location.protocol==="https:"?"wss":"ws";
  state.ws=new WebSocket(`${proto}://${location.host}/ws/events`);
  state.ws.onopen=()=>{$("last-updated").prepend("● ");};
  state.ws.onmessage=async(e)=>{
    try{
      const evt=JSON.parse(e.data);
      if(evt.type==="event"){
        notify("新事件："+labels[evt.kind]+"（"+labels[evt.severity]+"）");
        if(state.view==="monitor"){state.offset=0;await loadEvents();}
      }
    }catch(_){}
  };
  state.ws.onclose=()=>{setTimeout(connectWS,3000);};
}
connectWS();
window.addEventListener("resize",()=>{drawMap();drawChart();drawImage("inference-canvas",state.inferenceImage,state.inferenceBoxes);drawAnnotation();});
setInterval(()=>{if(!document.hidden&&state.view==="monitor")run(refresh);},15000);
if(document.modelContext?.registerTool){
  const lifecycle=new AbortController();
  window.addEventListener("pagehide",()=>lifecycle.abort(),{once:true});
  Promise.resolve(document.modelContext.registerTool({
    name:"filter_road_events",description:"Filter the visible event queue by status; does not modify events.",
    inputSchema:{type:"object",properties:{status:{type:"string",enum:["","open","acknowledged","resolved","dismissed"]}},required:["status"],additionalProperties:false},
    annotations:{readOnlyHint:true,untrustedContentHint:true},
    async execute(input){
      if(!input||Object.keys(input).length!==1||!["","open","acknowledged","resolved","dismissed"].includes(input.status))throw new Error("Invalid status");
      $("status-filter").value=input.status;state.offset=0;await changeView("monitor");
      return {total:state.total,items:state.events.map(e=>({id:e.id,kind:e.kind,status:e.status}))};
    }
  },{signal:lifecycle.signal})).catch(()=>{});
}
run(refresh);
