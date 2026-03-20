
    const idleScreen = document.getElementById('idleScreen');
    const dashMode = document.getElementById('dashMode');
    const speechBubble = document.getElementById('speechBubble');
    const idleTitle = document.getElementById('idleTitle');
    const idleSub = document.getElementById('idleSub');
    const idleCard = document.getElementById('idleCard');
    const mainFace = document.getElementById('mainFace');

    const dashStatusText = document.getElementById('dashStatusText');
    const currentDrink = document.getElementById('currentDrink');
    const stepValue = document.getElementById('stepValue');
    const etaValue = document.getElementById('etaValue');
    const etaBar = document.getElementById('etaBar');
    const stateLabel = document.getElementById('stateLabel');
    const queueState = document.getElementById('queueState');
    const ingredientValue = document.getElementById('ingredientValue');
    const queueSub = document.getElementById('queueSub');
    const queueList = document.getElementById('queueList');
    const queueEmpty = document.getElementById('queueEmpty');
    const miniBubble = document.getElementById('miniBubble');
    const lastRefresh = document.getElementById('lastRefresh');

    let idleTimer = null;
    let pollTimer = null;
    let lastDoneKey = null;
    let prevCurrentKey = null;
    let currentMode = 'idle';

    const phases = [
      { face: 'smile-big', card: { type: 'none' }, bubble: "Hehe... I'm ready!" },
      { face: 'wink', card: { type: 'text', text: 'LOADING...' }, bubble: 'Loading...' },
      { face: 'surprised', card: { type: 'text', text: 'SLEEP
JAM' }, bubble: 'Sleep jam!' },
      { face: 'look-left', card: { type: 'text', text: 'BACK
IN
5 MINUTES' }, bubble: 'Back in 5 minutes!' },
      { face: 'look-right', card: { type: 'textDark', text: 'YOU
LOSE' }, bubble: 'Bleep bloop!' },
      { face: 'smile-big', card: { type: 'text', text: 'ORDER
UP?' }, bubble: 'Hi friend!' }
    ];

    function fmt(sec){
      sec = Math.max(0, parseInt(sec || 0, 10));
      const m = Math.floor(sec / 60);
      const s = sec % 60;
      return m > 0 ? `${m}m ${String(s).padStart(2,'0')}s` : `${s}s`;
    }

    function speak(text){
      try{
        if(!('speechSynthesis' in window) || !text) return;
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(text);
        u.rate = 1.04;
        u.pitch = 1.45;
        u.volume = 1;
        const voices = window.speechSynthesis.getVoices();
        const preferred = voices.find(v => /samantha|ava|victoria|karen|moira/i.test(v.name)) || voices.find(v => /^en/i.test(v.lang));
        if(preferred) u.voice = preferred;
        window.speechSynthesis.speak(u);
      }catch(e){}
    }

    function showBubble(text, ms=1800){
      speechBubble.textContent = text || '';
      speechBubble.classList.add('show');
      clearTimeout(showBubble._t);
      showBubble._t = setTimeout(() => speechBubble.classList.remove('show'), ms);
    }

    function renderCard(card){
      idleCard.classList.remove('show');
      setTimeout(() => {
        if(card.type === 'none'){
          idleCard.className = 'idleCard';
          idleCard.innerHTML = '';
        } else if(card.type === 'textDark'){
          idleCard.className = 'idleCard dark show';
          idleCard.innerHTML = `<div class="tileText pixel" style="color:#9df5df">${card.text.replace(/
/g,'<br>')}</div>`;
        } else {
          idleCard.className = 'idleCard show';
          idleCard.innerHTML = `<div class="tileText pixel">${card.text.replace(/
/g,'<br>')}</div>`;
        }
      }, 120);
    }

    function startIdle(){
      clearInterval(idleTimer);
      currentMode = 'idle';
      dashMode.classList.remove('show');
      idleScreen.className = 'idleScreen show smile-big';
      idleTitle.textContent = 'Waiting for orders';
      idleSub.textContent = 'BMO is playing around on screen.';
      mainFace.className = 'mainFace floaty';
      renderCard({ type: 'none' });
      showBubble("Hehe... I'm ready!", 1800);

      let idx = 0;
      const runIdleCycle = () => {
        idx = (idx + 1) % phases.length;
        const phase = phases[idx];
        idleScreen.className = `idleScreen show ${phase.face}`;
        renderCard(phase.card);
        showBubble(phase.bubble, 1800);
      };

      setTimeout(runIdleCycle, 2000);
      idleTimer = setInterval(runIdleCycle, 15000);
    }

    function showComplete(done){
      clearInterval(idleTimer);
      currentMode = 'complete';
      dashMode.classList.remove('show');
      idleScreen.className = 'idleScreen show complete';
      idleTitle.textContent = 'Drink completed';
      idleSub.textContent = done && done.drinkName ? done.drinkName : 'Your drink is ready';
      mainFace.className = 'mainFace bouncy';
      renderCard({ type: 'none' });
      showBubble('Yay, your drink has been completed.', 3400);
      speak('Yay, your drink has been completed.');
      setTimeout(() => {
        mainFace.className = 'mainFace floaty';
      }, 3500);
    }

    function showActive(data){
      clearInterval(idleTimer);
      currentMode = 'active';
      idleScreen.classList.remove('show');
      dashMode.classList.add('show');

      const current = data.current || null;
      const queue = Array.isArray(data.queue) ? data.queue : [];
      const currentName = current && current.drinkName ? current.drinkName : 'No active drink';
      const stepsDone = current && current.currentStep ? parseInt(current.currentStep, 10) : 0;
      const stepsTotal = current && current.totalSteps ? parseInt(current.totalSteps, 10) : 0;
      const etaSec = current && current.etaSeconds != null ? parseInt(current.etaSeconds, 10) : null;
      const ingredient = current && current.currentIngredient ? current.currentIngredient : 'Waiting...';
      const qCount = queue.length;

      dashStatusText.textContent = current ? 'Now making' : 'Queue active';
      currentDrink.textContent = currentName;
      stepValue.textContent = `${stepsDone || 0}/${stepsTotal || 0}`;
      etaValue.textContent = etaSec == null ? '--s' : fmt(etaSec);
      ingredientValue.textContent = ingredient;
      stateLabel.textContent = current ? 'In progress' : 'Queued';
      queueState.textContent = qCount ? `${qCount} drink(s)` : 'Queue empty';
      queueSub.textContent = `${qCount} active drink(s)`;
      lastRefresh.textContent = new Date().toLocaleTimeString([], {hour:'numeric', minute:'2-digit', second:'2-digit'});

      if(current && prevCurrentKey !== String(current.id || current.drinkName || '')){
        miniBubble.textContent = 'Working on your drink!';
        miniBubble.classList.add('show');
        clearTimeout(miniBubble._t);
        miniBubble._t = setTimeout(() => miniBubble.classList.remove('show'), 1600);
      }
      prevCurrentKey = current ? String(current.id || current.drinkName || '') : null;

      const totalEta = current && current.totalEtaSeconds ? parseInt(current.totalEtaSeconds, 10) : null;
      const percent = (!current || etaSec == null || !totalEta || totalEta <= 0)
        ? 0
        : Math.max(0, Math.min(100, Math.round(((totalEta - etaSec) / totalEta) * 100)));
      etaBar.style.width = `${percent}%`;

      queueList.innerHTML = '';
      if(!qCount){
        queueEmpty.classList.add('show');
      } else {
        queueEmpty.classList.remove('show');
        queue.forEach((item, idx) => {
          const div = document.createElement('div');
          div.className = 'queueItem';
          const drink = item.drinkName || `Drink ${idx+1}`;
          const pos = item.position != null ? item.position : idx + 1;
          const st = item.status || (idx === 0 ? 'In Progress' : 'Pending');
          const eta = item.etaSeconds != null ? fmt(item.etaSeconds) : '--';
          div.innerHTML = `<div class="qDrink">${drink}</div><div class="qMeta">Position #${pos} • ${st} • ETA ${eta}</div>`;
          queueList.appendChild(div);
        });
      }
    }

    async function tick(){
      try{
        const res = await fetch('/api/live-display', {cache:'no-store'});
        const data = await res.json();
        if(!data.ok) throw new Error('bad response');

        const current = data.current || null;
        const queue = Array.isArray(data.queue) ? data.queue : [];
        const hasActive = !!current || queue.length > 0;
        const done = data.lastDone || null;
        const doneKey = done ? `${done.drinkName || ''}-${done.secondsAgo || 0}` : null;

        if(done && done.secondsAgo <= 10 && doneKey !== lastDoneKey && !hasActive){
          lastDoneKey = doneKey;
          prevCurrentKey = null;
          showComplete(done);
          return;
        }

        if(hasActive){
          showActive(data);
          return;
        }

        prevCurrentKey = null;
        if(currentMode !== 'idle' || !idleTimer){
          startIdle();
        }
      } catch(err){
        prevCurrentKey = null;
        if(currentMode !== 'idle'){
          startIdle();
        }
      }
    }

    if('speechSynthesis' in window){ window.speechSynthesis.getVoices(); }
    startIdle();

    if(window.location.protocol !== 'file:'){
      tick();
      pollTimer = setInterval(tick, 1000);
    }
  