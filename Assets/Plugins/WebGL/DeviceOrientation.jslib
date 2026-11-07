mergeInto(LibraryManager.library, {
  // Called once from HeadLook.Start(). Sets up the gyro listener and exposes
  // window.floodVR.requestPermission() for the template's "Enter VR" tap (iOS).
  FloodVR_StartOrientation: function (goNamePtr, methodPtr) {
    var go = UTF8ToString(goNamePtr);
    var method = UTF8ToString(methodPtr);

    function toQuaternion(alpha, beta, gamma) {
      var _x = (beta  || 0) * Math.PI / 180;
      var _y = (gamma || 0) * Math.PI / 180;
      var _z = (alpha || 0) * Math.PI / 180;
      var cX = Math.cos(_x/2), cY = Math.cos(_y/2), cZ = Math.cos(_z/2);
      var sX = Math.sin(_x/2), sY = Math.sin(_y/2), sZ = Math.sin(_z/2);
      // ZXY intrinsic order (W3C deviceorientation convention)
      return [
        sX*cY*cZ - cX*sY*sZ,
        cX*sY*cZ + sX*cY*sZ,
        cX*cY*sZ + sX*sY*cZ,
        cX*cY*cZ - sX*sY*sZ
      ];
    }

    function send(csv) {
      var inst = (typeof unityInstance !== 'undefined' && unityInstance) ||
                 (window.unityInstance) ||
                 (typeof gameInstance !== 'undefined' && gameInstance);
      if (inst) inst.SendMessage(go, method, csv);
    }

    function handler(e) {
      if (e.alpha === null || e.alpha === undefined) return;
      var q = toQuaternion(e.alpha, e.beta, e.gamma);
      send(q[0].toFixed(5)+","+q[1].toFixed(5)+","+q[2].toFixed(5)+","+q[3].toFixed(5));
    }

    function attach() {
      window.removeEventListener('deviceorientation', handler, true);
      window.addEventListener('deviceorientation', handler, true);
    }

    window.floodVR = window.floodVR || {};
    window.floodVR.attach = attach;
    window.floodVR.requestPermission = function () {
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

    // Android/desktop fire without a permission gesture; iOS waits for the tap.
    var needsGesture = (typeof DeviceOrientationEvent !== 'undefined' &&
                        typeof DeviceOrientationEvent.requestPermission === 'function');
    if (!needsGesture) attach();
  }
});
