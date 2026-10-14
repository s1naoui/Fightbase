(function(){
  "use strict";
  var key="fightbase-theme";
  var root=document.documentElement;
  function read(){try{return localStorage.getItem(key)==="light"?"light":"dark"}catch(_){return "dark"}}
  function apply(theme){
    root.dataset.theme=theme;
    root.style.colorScheme=theme;
    document.querySelectorAll("[data-theme-toggle]").forEach(function(button){
      var light=theme==="light";
      button.textContent=light?"☾ Dunkelmodus":"☀ Hellmodus";
      button.setAttribute("aria-label",light?"Dunkelmodus aktivieren":"Hellmodus aktivieren");
      button.setAttribute("aria-pressed",String(light));
      button.title=light?"Zur dunklen Ansicht wechseln":"Zur hellen Ansicht wechseln";
    });
  }
  apply(read());
  document.addEventListener("click",function(event){
    var button=event.target.closest("[data-theme-toggle]");
    if(!button)return;
    var next=root.dataset.theme==="light"?"dark":"light";
    try{localStorage.setItem(key,next)}catch(_){}
    apply(next);
  });
  document.addEventListener("DOMContentLoaded",function(){apply(read())});
})();
