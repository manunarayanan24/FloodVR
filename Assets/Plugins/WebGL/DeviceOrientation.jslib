mergeInto(LibraryManager.library, {
  // Called once from HeadLook.Start(). Sets up the gyro listener and exposes
  // window.floodVR.requestPermission() for the template's "Enter VR" tap (iOS).
  //
  // Sends the CAMERA orientation (three.js DeviceOrientationControls convention:
  // right-handed, Y up, camera looks down -Z, corrected for the phone being held in
  // landscape inside the viewer) as "x,y,z,w". HeadLook.cs converts it to Unity's
  // left-handed frame with (-x, -y, z, w).
  FloodVR_StartOrientation: function (goNamePtr, methodPtr) {
    var go = UTF8ToString(goNamePtr);
    var method = UTF8ToString(methodPtr);
    var D2R = Math.PI / 180;

    function mul(a, b) {
      return [
        a[0]*b[3] + a[3]*b[0] + a[1]*b[2] - a[2]*b[1],
        a[1]*b[3] + a[3]*b[1] + a[2]*b[0] - a[0]*b[2],
        a[2]*b[3] + a[3]*b[2] + a[0]*b[1] - a[1]*b[0],
        a[3]*b[3] - a[0]*b[0] - a[1]*b[1] - a[2]*b[2]
      ];
    }

    function screenAngle() {
      var a = 0;
      if (window.screen && window.screen.orientation && typeof window.screen.orientation.angle === 'number') {
        a = window.screen.orientation.angle;
      } else if (typeof window.orientation === 'number') {
        a = window.orientation;
      }
      if (a > 180) a -= 360;
      return a;
    }

    function toCameraQuaternion(alpha, beta, gamma, orient) {
      // Euler order YXZ with (x = beta, y = alpha, z = -gamma)
      var x = beta * D2R, y = alpha * D2R, z = -gamma * D2R;
      var c1 = Math.cos(x / 2), c2 = Math.cos(y / 2), c3 = Math.cos(z / 2);
      var s1 = Math.sin(x / 2), s2 = Math.sin(y / 2), s3 = Math.sin(z / 2);
      var q = [
        s1*c2*c3 + c1*s2*s3,
        c1*s2*c3 - s1*c2*s3,
        c1*c2*s3 - s1*s2*c3,
        c1*c2*c3 + s1*s2*s3
      ];
      var h = Math.sqrt(0.5);
      q = mul(q, [-h, 0, 0, h]);                       // camera looks out the back of the phone
      var o = -orient * D2R / 2;
      q = mul(q, [0, 0, Math.sin(o), Math.cos(o)]);    // compensate screen rotation (landscape)
      return q;
    }

    function send(csv) {
      var inst = (typeof unityInstance !== 'undefined' && unityInstance) ||
                 (window.unityInstance) ||
                 (typeof gameInstance !== 'undefined' && gameInstance);
      if (inst) inst.SendMessage(go, method, csv);
    }

    function handler(e) {
      if (e.alpha === null || e.alpha === undefined) return;
      var q = toCameraQuaternion(e.alpha || 0, e.beta || 0, e.gamma || 0, screenAngle());
      send(q[0].toFixed(5)+","+q[1].toFixed(5)+","+q[2].toFixed(5)+","+q[3].toFixed(5));
    }

    function attach() {
      window.removeEventListener('deviceorientation', handler, true);
      window.addEventListener('deviceorientation', handler, true);
    }

    window.floodVR = window.floodVR || {};
    window.floodVR.attach = attach;
    window.floodVR.requestPermission = function () {
      window.floodVR.enteredAt = Date.now(); // tap-to-talk ignores taps right after "Enter VR"
      try {
        if (typeof DeviceOrientationEvent !== 'undefined' &&
            typeof DeviceOrientationEvent.requestPermission === 'function') {
          DeviceOrientationEvent.requestPermission()
            .then(function (res) { if (res === 'granted') attach(); })
            .catch(function () { attach(); });
        } else {
          attach();
        }
      } catch (err) { attach(); }
    };
    // Lets the page re-centre the view: window.floodVR.recenter()
    window.floodVR.recenter = function () { send_recenter(); };
    function send_recenter() {
      var inst = (typeof unityInstance !== 'undefined' && unityInstance) ||
                 (window.unityInstance) ||
                 (typeof gameInstance !== 'undefined' && gameInstance);
      if (inst) inst.SendMessage(go, 'Recenter');
    }

    // Android/desktop fire without a permission gesture; iOS waits for the tap.
    var needsGesture = (typeof DeviceOrientationEvent !== 'undefined' &&
                        typeof DeviceOrientationEvent.requestPermission === 'function');
    if (!needsGesture) attach();
  },

  // Reads ?name=value from the page URL. A value that is present is also saved in
  // localStorage, because launching from the iOS home screen drops the query string;
  // when the URL has no value the saved one is returned. Empty string if neither exists.
  FloodVR_GetQueryParam: function (namePtr) {
    var name = UTF8ToString(namePtr);
    var val = '';
    var key = 'floodvr_' + name;
    try {
      var v = new URLSearchParams(window.location.search).get(name);
      if (v !== null && v !== '') {
        val = v;
        try { window.localStorage.setItem(key, v); } catch (e1) {}
      } else {
        try { val = window.localStorage.getItem(key) || ''; } catch (e2) {}
      }
    } catch (e) {}
    var size = lengthBytesUTF8(val) + 1;
    var buf = _malloc(size);
    stringToUTF8(val, buf, size);
    return buf;
  },

  // Tap-to-talk. Safari's speech recognition must be started inside a real tap, so the tap
  // handler lives here in JS. Results/state are sent back to the Unity object `goName`:
  //   OnSpeechState("listening" | "idle" | "unsupported" | "error:<code>")
  //   OnSpeechResult("<transcript>")
  FloodVR_InitSpeech: function (goNamePtr) {
    var go = UTF8ToString(goNamePtr);
    function inst() {
      return (typeof unityInstance !== 'undefined' && unityInstance) || window.unityInstance ||
             (typeof gameInstance !== 'undefined' && gameInstance);
    }
    function send(method, msg) { var i = inst(); if (i) i.SendMessage(go, method, msg); }

    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    window.floodVR = window.floodVR || {};
    if (!SR) { send('OnSpeechState', 'unsupported'); return; }

    var rec = new SR();
    rec.lang = 'en-US';
    rec.continuous = false;
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    var listening = false;

    rec.onstart = function () { listening = true; send('OnSpeechState', 'listening'); };
    rec.onresult = function (e) {
      try {
        var r = e.results[e.results.length - 1];
        var txt = r[0].transcript || '';
        if (txt) send('OnSpeechResult', txt);
      } catch (err) {}
    };
    rec.onerror = function (e) { send('OnSpeechState', 'error:' + (e && e.error ? e.error : 'unknown')); };
    rec.onend = function () { listening = false; send('OnSpeechState', 'idle'); };

    function onTap() {
      var f = window.floodVR;
      if (!f.enteredAt || Date.now() - f.enteredAt < 1500) return; // that tap was "Enter VR"
      if (listening) { try { rec.stop(); } catch (e1) {} return; }
      try { rec.start(); } catch (e2) { send('OnSpeechState', 'error:start-failed'); }
    }
    // Unity's canvas may swallow the synthetic click, so listen to touchend too (debounced).
    var lastTap = 0;
    function once() {
      var now = Date.now();
      if (now - lastTap < 700) return;
      lastTap = now;
      onTap();
    }
    document.addEventListener('touchend', once, true);
    document.addEventListener('click', once, true);
  },

  // Reads text aloud (the voice reply). Works after the user has tapped the page.
  FloodVR_Speak: function (textPtr) {
    try {
      var text = UTF8ToString(textPtr);
      if (!text || !window.speechSynthesis) return;
      window.speechSynthesis.cancel();
      var u = new SpeechSynthesisUtterance(text);
      u.lang = 'en-US';
      window.speechSynthesis.speak(u);
    } catch (e) {}
  }
});
