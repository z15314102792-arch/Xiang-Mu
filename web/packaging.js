// Xiang Mu 实际包装参数编辑器；最终全部发给后端 FFmpeg 渲染。
let flowerRows=[];
const packageDefaults={subtitleEnabled:true,subtitleSize:46,subtitleBottom:13,
 subtitleColor:"#FFFFFF",subtitleAnimation:"fade",openingZoom:false,
 bgmEnabled:false,bgmVolume:.12,sfxEnabled:false,sfxTime:.6,sfxVolume:.14,flowers:[]};
function restorePackage(j){
 const c={...packageDefaults,...(j.packaging||{})};
 for(const k of ["subtitleEnabled","openingZoom","bgmEnabled","sfxEnabled"])el(k).checked=c[k];
 for(const k of ["subtitleSize","subtitleBottom","subtitleColor","subtitleAnimation","bgmVolume","sfxTime","sfxVolume"])el(k).value=c[k];
 flowerRows=structuredClone(c.flowers||[]);
 renderFlowers();
 el("bgmState").textContent=j.audioFiles?.bgm?"已上传 "+j.audioFiles.bgm:"未上传背景音乐";
 el("sfxState").textContent=j.audioFiles?.sfx?"已上传 "+j.audioFiles.sfx:"未上传音效";
 el("packageState").textContent=j.packaging?"已恢复当前项目的包装配置":"使用初始包装样式；可编辑保存";
}
function packagingConfig(){
 const c={flowers:flowerRows.map(x=>({...x}))};
 for(const k of ["subtitleEnabled","openingZoom","bgmEnabled","sfxEnabled"])c[k]=el(k).checked;
 for(const k of ["subtitleSize","subtitleBottom","bgmVolume","sfxTime","sfxVolume"])c[k]=Number(el(k).value);
 for(const k of ["subtitleColor","subtitleAnimation"])c[k]=el(k).value;
 return c;
}
function renderFlowers(){
 const root=el("flowerList");root.innerHTML="";
 if(!flowerRows.length){let p=document.createElement("div");p.className="help";p.textContent="尚无花字。点右侧“添加花字”并填写成片时间。";root.appendChild(p);return}
 const fields=[
 ["text","花字文案","text",null],
 ["start","开始秒数","number",null],
 ["end","结束秒数","number",null],
 ["position","位置","select",[["upper","上方"],["center","正中"],["lower","下方"]]],
 ["animation","入场动画","select",[["pop","弹入"],["fade","淡入"],["rise","上浮"],["none","静态"]]],
 ["color","颜色","select",[["#FFD85C","金黄"],["#FFFFFF","白"],["#7CE8CE","薄荷绿"],["#FF9FAF","粉色"],["#9ED4FF","蓝色"]]]
 ];
 flowerRows.forEach((row,index)=>{
  const box=document.createElement("div");box.className="clip";
  const head=document.createElement("div");head.className="cliptop";
  const title=document.createElement("strong");title.textContent="重点花字 "+(index+1);
  const rm=document.createElement("button");rm.className="btn";rm.textContent="删除";rm.onclick=()=>{flowerRows.splice(index,1);renderFlowers()};
  head.append(title,rm);box.appendChild(head);
  const inputs=document.createElement("div");inputs.className="controls";inputs.style.gridTemplateColumns="repeat(3,1fr)";
  for(const [key,label,kind,choices] of fields){
   const wrap=document.createElement("label");wrap.textContent=label;
   let input=document.createElement(kind==="select"?"select":"input");
   if(kind==="select"){choices.forEach(([val,name])=>{let o=document.createElement("option");o.value=val;o.textContent=name;input.appendChild(o)})}
   else{input.type=kind;if(kind==="number"){input.step="0.05";input.min=0}}
   input.value=row[key];
   input.onchange=()=>{row[key]=kind==="number"?Number(input.value):input.value};
   if(key==="text")input.maxLength=24;
   wrap.appendChild(input);inputs.appendChild(wrap);
  }
  box.appendChild(inputs);root.appendChild(box);
 });
}
async function uploadTrack(kind){
 if(!job){err("请先导入视频");return}
 const picker=el(kind+"File"),file=picker.files?.[0];
 if(!file){err("请先选择 "+kind.toUpperCase()+" 文件");return}
 if(file.size>50000000){err("音频超过50MB限制");return}
 const button=el(kind==="bgm"?"sendBgm":"sendSfx");
 button.disabled=true;
 try{
  info("正在上传 "+kind.toUpperCase()+" 到本机项目工作区……");
  const url="/api/real/audio?id="+encodeURIComponent(job.id)+"&kind="+kind+"&name="+encodeURIComponent(file.name);
  const resp=await fetch(url,{method:"POST",headers:{"X-Workflow-Local":"1"},body:file});
  const d=await resp.json();if(!resp.ok)throw Error(d.error||resp.status);
  job=d;
  el(kind+"State").textContent="已上传 "+d.audioFiles[kind];
  el("downloads").innerHTML="";
  ok(kind.toUpperCase()+" 已保存，可以勾选启用并设置音量");
 }catch(e){err("上传失败："+e.message)}finally{button.disabled=false}
}
async function savePackageUI(){
 if(!job)return err("先导入视频");
 try{
  const r=await post("/api/real/packaging",{id:job.id,packaging:packagingConfig()});
  job=r;el("downloads").innerHTML="";
  el("packageState").textContent="✔ 已保存 "+(r.packaging?.flowers?.length||0)+" 条花字与字幕/配音设置";
  ok("包装设置已保存。点击左侧“渲染成片”后才会写入 MP4。");
 }catch(e){err("包装配置错误："+e.message)}
}
window.addEventListener("DOMContentLoaded",()=>{
 el("addFlower").onclick=()=>{
  if(flowerRows.length>=30)return err("最多添加30条花字");
  const end=rows.filter(x=>x.keep).reduce((a,x)=>a+x.end-x.start,0);
  const start=Math.min(Math.max(0,end-1.4),Math.max(.5,Number((end*.2).toFixed(2))));
  flowerRows.push({text:"重点总结",start:Number(start.toFixed(2)),end:Number((start+1.1).toFixed(2)),
                   position:"upper",animation:"pop",color:"#FFD85C"});
  renderFlowers();
 };
 el("sendBgm").onclick=()=>uploadTrack("bgm");
 el("sendSfx").onclick=()=>uploadTrack("sfx");
 el("savePackage").onclick=savePackageUI;
});
