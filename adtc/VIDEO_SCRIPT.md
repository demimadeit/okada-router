# Gate 1 video — 2:00 max, one continuous screen recording + voiceover

Record with QuickTime (screen) or OBS; phone voiceover is fine. One take is
better than polish. Keep the terminal and the app side by side.

**0:00–0:15 — the problem (talking over a slide or the app)**
> "Nigeria had twenty-seven thousand fibre cuts last year. Every AI app
> assumes perfect internet — when the network drops, they die. This is
> Okada Router: AI that never stops answering."

**0:15–0:35 — normal operation**
- App open at http://127.0.0.1:8080. Ask: *"List the documents a rider
  needs to register."*
- Point at the meta line: **via cloud · fast**.
> "On a good connection Okada routes to a frontier cloud model."

**0:35–1:00 — degradation**
- Tap the status pill → tap `3g`, ask again a different question.
- Meta line shows **cloud·small**.
> "The network degrades — Okada notices and switches to a smaller, cheaper
> model. Less data, lower cost. The user just sees an answer."

**1:00–1:30 — the killer moment: offline**
- Tap `offline`. Ask: *"Draft a message telling my customer the delivery
  is delayed."*
- Answer appears anyway; meta line shows **on-device**.
> "Now there is no internet at all. This answer came from a three-billion-
> parameter model running locally through llama.cpp — on this 8GB laptop,
> no GPU, no cloud, no data cost."

**1:30–1:50 — queue and sync**
- (llama-server stopped beforehand for this beat, still offline) Ask
  something; meta shows **queued**. Tap `excellent`; queued answer arrives.
> "If even the local model is unavailable, nothing is lost — requests queue
> and deliver themselves when the connection returns."

**1:50–2:00 — close**
> "Okada Router. Cloud when you have it, on-device when you don't, queued
> when there's nothing. Built for how Africa is actually connected."
