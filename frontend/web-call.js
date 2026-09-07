(function () {
  "use strict";

  var AudioContextClass = window.AudioContext || window.webkitAudioContext;

  function pcmToBase64(samples) {
    var bytes = new Uint8Array(samples.buffer);
    var binary = "";
    for (var index = 0; index < bytes.length; index += 1) {
      binary += String.fromCharCode(bytes[index]);
    }
    return window.btoa(binary);
  }

  function base64ToPCM(value) {
    var binary = window.atob(value);
    var bytes = new Uint8Array(binary.length);
    for (var index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return new Int16Array(bytes.buffer);
  }

  function downsample(input, sourceRate, targetRate) {
    if (sourceRate === targetRate) return input;
    var ratio = sourceRate / targetRate;
    var output = new Float32Array(Math.round(input.length / ratio));
    var offset = 0;
    for (var index = 0; index < output.length; index += 1) {
      var nextOffset = Math.round((index + 1) * ratio);
      var total = 0;
      var count = 0;
      for (; offset < nextOffset && offset < input.length; offset += 1) {
        total += input[offset];
        count += 1;
      }
      output[index] = count ? total / count : 0;
    }
    return output;
  }

  function toPCM16(input) {
    var output = new Int16Array(input.length);
    for (var index = 0; index < input.length; index += 1) {
      var sample = Math.max(-1, Math.min(1, input[index]));
      output[index] = sample < 0 ? sample * 32768 : sample * 32767;
    }
    return output;
  }

  function socketURL() {
    var protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    var host = window.location.host;
    if ((host === "127.0.0.1:8080" || host === "localhost:8080")) {
      host = host.replace(":8080", ":8000");
    }
    return protocol + "//" + host + "/ws/voice-chat";
  }

  function setup(creator, track) {
    var form = document.querySelector("#web-call-form");
    if (!form || !AudioContextClass || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      var unsupported = document.querySelector("#web-call-unsupported");
      if (unsupported) unsupported.hidden = false;
      var unsupportedButton = document.querySelector("#web-call-start");
      if (unsupportedButton) unsupportedButton.disabled = true;
      return;
    }

    var startButton = document.querySelector("#web-call-start");
    var endButton = document.querySelector("#web-call-end");
    var muteButton = document.querySelector("#web-call-mute");
    var preCall = document.querySelector("#web-call-pre");
    var liveCall = document.querySelector("#web-call-live");
    var badge = document.querySelector("#call-availability");
    var status = document.querySelector("#web-call-status");
    var timer = document.querySelector("#web-call-timer");
    var transcript = document.querySelector("#web-call-transcript");
    var errorBox = document.querySelector("#web-call-error");
    var callOrb = document.querySelector("#web-call-orb");
    var consent = document.querySelector("#web-call-consent");
    var consentError = document.querySelector("#web-consent-error");

    var socket = null;
    var stream = null;
    var audioContext = null;
    var microphone = null;
    var processor = null;
    var silentGain = null;
    var playbackCursor = 0;
    var playbackSources = [];
    var callStartedAt = 0;
    var timerInterval = null;
    var limitTimeout = null;
    var muted = false;
    var ending = false;
    var responseDone = false;
    var captureStarted = false;
    var lastAudioSequence = 0;
    var lastTranscriptKey = "";
    var callToken = "";

    function setState(next, label) {
      liveCall.dataset.state = next;
      callOrb.dataset.state = next;
      status.textContent = label;
    }

    function showError(message) {
      errorBox.hidden = false;
      errorBox.textContent = message;
    }

    function addTranscript(speaker, text) {
      var transcriptKey = speaker + "\n" + String(text || "").trim().toLowerCase();
      if (!text || transcriptKey === lastTranscriptKey) return;
      lastTranscriptKey = transcriptKey;
      var empty = transcript.querySelector(".transcript-empty");
      if (empty) empty.remove();
      var row = document.createElement("p");
      row.className = "transcript-line " + (speaker === "You" ? "user" : "creator");
      var strong = document.createElement("strong");
      strong.textContent = speaker;
      var span = document.createElement("span");
      span.textContent = text;
      row.appendChild(strong);
      row.appendChild(span);
      transcript.appendChild(row);
      transcript.scrollTop = transcript.scrollHeight;
    }

    function updateTimer() {
      var seconds = Math.max(0, Math.floor((Date.now() - callStartedAt) / 1000));
      var minutes = Math.floor(seconds / 60);
      timer.textContent = String(minutes).padStart(2, "0") + ":" + String(seconds % 60).padStart(2, "0");
    }

    function stopPlayback() {
      playbackSources.forEach(function (source) {
        try { source.stop(); } catch (error) { /* already stopped */ }
      });
      playbackSources = [];
      playbackCursor = audioContext ? audioContext.currentTime : 0;
    }

    function playPCM(encoded) {
      if (!audioContext || !encoded || ending) return;
      var pcm = base64ToPCM(encoded);
      var buffer = audioContext.createBuffer(1, pcm.length, 16000);
      var channel = buffer.getChannelData(0);
      for (var index = 0; index < pcm.length; index += 1) channel[index] = pcm[index] / 32768;
      var source = audioContext.createBufferSource();
      source.buffer = buffer;
      source.connect(audioContext.destination);
      playbackCursor = Math.max(playbackCursor, audioContext.currentTime + 0.035);
      source.start(playbackCursor);
      playbackCursor += buffer.duration;
      playbackSources.push(source);
      source.addEventListener("ended", function () {
        playbackSources = playbackSources.filter(function (item) { return item !== source; });
        if (responseDone && playbackSources.length === 0 && !ending) setState("listening", "Listening");
      }, { once: true });
    }

    function startCapture() {
      if (captureStarted || ending) return;
      captureStarted = true;
      microphone = audioContext.createMediaStreamSource(stream);
      processor = audioContext.createScriptProcessor(4096, 1, 1);
      silentGain = audioContext.createGain();
      silentGain.gain.value = 0;
      processor.onaudioprocess = function (event) {
        if (!socket || socket.readyState !== WebSocket.OPEN || muted || ending) return;
        var input = event.inputBuffer.getChannelData(0);
        var sampled = downsample(input, audioContext.sampleRate, 16000);
        socket.send(JSON.stringify({ event: "audio", data: pcmToBase64(toPCM16(sampled)) }));
      };
      microphone.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(audioContext.destination);
      setState("listening", "Listening");
    }

    function handleMessage(event) {
      var message;
      try { message = JSON.parse(event.data); } catch (error) { return; }
      if (message.event === "ready") {
        startCapture();
        callStartedAt = Date.now();
        updateTimer();
        timerInterval = window.setInterval(updateTimer, 1000);
        var callLimitSeconds = Math.max(60, Math.min(Number(creator.max_call_seconds) || 300, 3600));
        limitTimeout = window.setTimeout(function () { endCall("This call reached its time limit."); }, callLimitSeconds * 1000);
        track("web_call_started", { creator_id: creator.id });
      } else if (message.event === "audio") {
        var sequence = Number(message.sequence || 0);
        if (sequence && sequence <= lastAudioSequence) return;
        if (sequence) lastAudioSequence = sequence;
        responseDone = false;
        setState("speaking", creator.name.split(/\s+/)[0] + " is speaking");
        playPCM(message.data);
      } else if (message.event === "user_transcript") {
        addTranscript("You", message.text || "");
      } else if (message.event === "transcript") {
        addTranscript(creator.name.split(/\s+/)[0], message.text || "");
      } else if (message.event === "state" && message.state === "thinking") {
        setState("thinking", "Thinking");
      } else if (message.event === "response_done") {
        responseDone = true;
        if (playbackSources.length === 0) setState("listening", "Listening");
      } else if (message.event === "barge_in") {
        stopPlayback();
        setState("listening", "Listening");
      } else if (message.event === "error") {
        failCall(message.message || "The live call disconnected.");
      }
    }

    async function endCall(message) {
      if (ending) return;
      ending = true;
      window.clearInterval(timerInterval);
      window.clearTimeout(limitTimeout);
      stopPlayback();
      if (processor) { processor.disconnect(); processor.onaudioprocess = null; }
      if (microphone) microphone.disconnect();
      if (silentGain) silentGain.disconnect();
      if (stream) stream.getTracks().forEach(function (item) { item.stop(); });
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ event: "stop" }));
        socket.close(1000, "Call ended");
      }
      if (audioContext && audioContext.state !== "closed") await audioContext.close();
      setState("ended", "Call ended");
      endButton.disabled = true;
      muteButton.disabled = true;
      if (message) showError(message);
      document.querySelector("#web-call-again").hidden = false;
      track("web_call_ended", { creator_id: creator.id });
    }

    async function failCall(message) {
      if (ending) return;
      await endCall();
      showError(message);
      setState("error", "Call failed");
    }

    fetch("/info", { cache: "no-store" }).then(function (response) { return response.json(); }).then(function (info) {
      var ready = Boolean(info.web_calls_configured);
      badge.className = "availability-badge " + (ready ? "available" : "unavailable");
      badge.textContent = ready ? "Web calls available" : "Web calls paused";
      startButton.disabled = !ready;
      if (!ready) startButton.querySelector(".btn-label").textContent = "Web calls are paused";
    }).catch(function () {
      badge.className = "availability-badge checking";
      badge.textContent = "Checked when started";
    });

    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      consentError.hidden = true;
      errorBox.hidden = true;
      if (!consent.checked) {
        consentError.hidden = false;
        consent.focus();
        return;
      }
      startButton.disabled = true;
      startButton.querySelector(".btn-label").textContent = "Opening microphone…";
      try {
        var admissionResponse = await fetch("/api/web-call-token", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ influencer_id: creator.id })
        });
        var admission = {};
        try { admission = await admissionResponse.json(); } catch (parseError) { /* empty */ }
        if (!admissionResponse.ok || !admission.token) {
          throw new Error(admission.detail || "A call spot could not be reserved. Try again.");
        }
        callToken = admission.token;
        audioContext = new AudioContextClass();
        await audioContext.resume();
        stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }, video: false });
        preCall.hidden = true;
        liveCall.hidden = false;
        setState("connecting", "Connecting securely");
        socket = new WebSocket(socketURL());
        socket.addEventListener("message", handleMessage);
        socket.addEventListener("open", function () {
          socket.send(JSON.stringify({ event: "start", influencer_id: creator.id, caller_name: document.querySelector("#user-name").value.trim(), call_token: callToken }));
        });
        socket.addEventListener("error", function () {
          failCall("The web call could not connect. Check your connection and try again.");
        });
        socket.addEventListener("close", function () {
          if (!ending) failCall("The web call disconnected.");
        });
      } catch (error) {
        startButton.disabled = false;
        startButton.querySelector(".btn-label").textContent = "Start web call";
        showError(error && error.name === "NotAllowedError" ? "Microphone access was blocked. Allow it in your browser settings and try again." : (error.message || "Your microphone could not start. Check that another app is not using it."));
        if (audioContext && audioContext.state !== "closed") await audioContext.close();
      }
    });

    muteButton.addEventListener("click", function () {
      muted = !muted;
      if (stream) stream.getAudioTracks().forEach(function (item) { item.enabled = !muted; });
      muteButton.setAttribute("aria-pressed", String(muted));
      muteButton.querySelector("span:last-child").textContent = muted ? "Unmute" : "Mute";
      if (muted) setState("muted", "Microphone muted"); else setState("listening", "Listening");
    });
    endButton.addEventListener("click", function () { endCall(); });
    document.querySelector("#web-call-again").addEventListener("click", function () { window.location.reload(); });
  }

  window.TACWebCall = { setup: setup };
})();
