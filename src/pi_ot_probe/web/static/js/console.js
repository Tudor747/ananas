const $ = id => document.getElementById(id);
const modules = [
  {node:"A",sensor:"nrf",name:"2.4 GHz · nRF",text:"Two compatible packet radios. Carrier observations are not Wi-Fi/BLE decoding."},
  {node:"A",sensor:"wifi",name:"Wi-Fi inventory",text:"ESP-native 2.4 GHz AP inventory. Raspberry Pi Wi-Fi remains in Network assessment."},
  {node:"A",sensor:"ble",name:"Bluetooth LE",text:"Advertisements exposed by the ESP BLE scan. No connection or payload capture."},
  {node:"B",sensor:"cc1101",name:"433 MHz · CC1101",text:"RSSI from the configured receiver; not proof of decoded packets."},
  {node:"B",sensor:"rfid",name:"RFID · RC522",text:"Compatible tag observations. Firmware masks tag identifiers."},
  {node:"C",sensor:"ir",name:"Infrared",text:"KY-022 reception and an explicitly selected single NEC frame via KY-005."},
];
let page = 0, selected = null, states = [], after = 0;
async function api(path, body) {
  const response = await fetch(path, body ? {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)} : {});
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : JSON.stringify(result.detail));
  return result;
}
function message(text) { $("status").textContent = text; }
function controls() {
  $("observe").disabled = !selected || !$("authorized").checked || !states.some(n => n.node === selected.node && n.connection === "online");
  $("transmit").disabled = $("observe").disabled;
  $("nrf-test").disabled = $("observe").disabled;
}
function renderMenu() {
  $("menu").replaceChildren();
  for (const item of modules.slice(page*2,page*2+2)) {
    const button = document.createElement("button"); button.className = "module" + (selected === item ? " selected" : "");
    button.textContent = item.name;
    const subtitle = document.createElement("span"); subtitle.textContent = `ESP32-${item.node}`;button.append(subtitle);
    button.addEventListener("click", () => {selected=item;$("selection").textContent=item.name;$("description").textContent=item.text;$("ir-transmit").hidden=item.sensor!=="ir";$("nrf-test").hidden=item.sensor!=="nrf";renderMenu();controls();});
    $("menu").append(button);
  }
  $("page-label").textContent=`${page+1} / 3`;$("previous").disabled=page===0;$("next").disabled=page===2;
}
async function command(node, name, args={}) {
  return api(`/api/nodes/${node}/commands`,{command:name,args,authorized:$("authorized").checked,operator:$("operator").value,purpose:$("purpose").value});
}
$("observe").onclick=async()=>{try{const r=await command(selected.node,"OBSERVE",{sensor:selected.sensor,duration_ms:Number($("duration").value)});message(`Request ${r.id} queued for ESP32-${selected.node}. Check the reply in the timeline.`);}catch(e){message(e.message);}};
$("transmit").onclick=async()=>{try{const hex=$("ir-code").value.trim();if(!/^[0-9a-fA-F]{1,8}$/.test(hex))throw new Error("Enter 1–8 hexadecimal digits.");await command("C","TRANSMIT",{code:parseInt(hex,16)});message("Single IR frame requested; check its reply.");}catch(e){message(e.message);}};
$("stop").onclick=async()=>{const live=states.filter(n=>n.connection==="online");const results=await Promise.allSettled(live.map(n=>command(n.node,"STOP")));message(results.some(r=>r.status==="rejected")?"Some STOP requests failed; disconnected nodes rely on their local timeout.":`STOP queued for ${live.length} node(s).`);};
$("authorized").onchange=controls;
$("nrf-test").onclick=async()=>{try{await command("A","TRANSMIT",{test:"nrf_link"});message("One nRF packet requested. Check the reply for matching reception on the second radio.");}catch(e){message(e.message);}};
$("previous").onclick=()=>{page=Math.max(0,page-1);renderMenu();};$("next").onclick=()=>{page=Math.min(2,page+1);renderMenu();};
let touchY=null;$("menu").addEventListener("touchstart",e=>{touchY=e.touches[0].clientY;},{passive:true});
$("menu").addEventListener("touchend",e=>{if(touchY!==null){const dy=e.changedTouches[0].clientY-touchY;if(Math.abs(dy)>45){page=Math.max(0,Math.min(2,page+(dy<0?1:-1)));renderMenu();}touchY=null;}},{passive:true});
async function refresh() {
  try {
    const [nodes, evidence] = await Promise.all([api("/api/nodes"),api(`/api/peripheral-events?after=${after}`)]);
    states=nodes.nodes;$("nodes").replaceChildren();
    for(const state of states){const card=document.createElement("div");card.className=`node ${state.connection}`;card.textContent=`ESP32-${state.node} · ${state.connection}`;const detail=document.createElement("span");detail.textContent=state.error||state.health;card.append(detail);$("nodes").append(card);}
    for(const event of evidence.events){if(event.kind==="reply"&&event.data.command==="STATUS")continue;const li=document.createElement("li");li.textContent=`${event.received_at} · ${event.node} · ${event.kind} · ${event.provenance}`;const pre=document.createElement("pre");pre.textContent=JSON.stringify(event.data,null,2);li.append(pre);$("events").prepend(li);}
    after=evidence.next_after;while($("events").children.length>60)$("events").lastChild.remove();controls();
  } catch(e){states=[];controls();for(const card of $("nodes").children){card.className="node";card.textContent="Connection status unavailable";}message(`Application unavailable: ${e.message}`);}
  setTimeout(refresh,1000);
}
renderMenu();message("Select a module. Unconfigured nodes require a local USB configuration.");refresh();
