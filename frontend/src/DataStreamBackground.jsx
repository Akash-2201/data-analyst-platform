import React, { useMemo } from "react";

/**
 * DataStreamBackground — Ambient animated tech background for the Auth screen.
 * 
 * Features 4 layered visual elements in the Datalyst brand palette (Violet #8B7CF6 & Emerald #34D399):
 * 1. Scrolling binary digits (sparse, low-opacity digital rain on the left third)
 * 2. Animated bar-chart silhouette (pulsing vertical bars with reflection on the center-right)
 * 3. Horizontal glowing scan lines / light beams crossing the canvas
 * 4. Floating glowing particles drifting upward around the data bars
 * 
 * Pure CSS animations, zero layout shift, pointer-events: none.
 */

// Stable binary sequence blocks for looping columns
const BINARY_SEQUENCES = [
  "1011001010011010010101101001001101011010",
  "0100101101101001010011010010110101001011",
  "1101010010110010100110100101011010010011",
  "0010110101001011011010010100110100101101",
  "1001011010010011010110100100101101101001",
  "0110100101001101001011010100101101101001",
];

// Profile of 10 bars (height in px, duration in s, delay in s, accent)
const BARS = [
  { height: 48, duration: 3.6, delay: -0.4, accent: "emerald" },
  { height: 86, duration: 4.2, delay: -1.8, accent: "emerald" },
  { height: 136, duration: 3.8, delay: -0.9, accent: "violet" },
  { height: 62, duration: 4.6, delay: -2.7, accent: "emerald" },
  { height: 108, duration: 3.2, delay: -1.2, accent: "violet" },
  { height: 168, duration: 4.0, delay: -0.3, accent: "emerald" },
  { height: 118, duration: 3.7, delay: -2.1, accent: "violet" },
  { height: 212, duration: 4.4, delay: -1.5, accent: "emerald" }, // Hero bar
  { height: 92, duration: 3.5, delay: -0.7, accent: "violet" },
  { height: 64, duration: 4.3, delay: -2.4, accent: "emerald" },
];

// 20 Floating ambient particles
const PARTICLES = [
  { x: 52, y: 72, size: 3, dur: 9.2, delay: -1.1, driftX: 18, color: "emerald", opacity: 0.65 },
  { x: 58, y: 64, size: 5, dur: 11.5, delay: -3.4, driftX: -14, color: "white", opacity: 0.8 },
  { x: 63, y: 76, size: 3, dur: 8.4, delay: -0.6, driftX: 12, color: "emerald", opacity: 0.7 },
  { x: 67, y: 58, size: 4, dur: 12.0, delay: -5.2, driftX: -16, color: "violet", opacity: 0.6 },
  { x: 71, y: 70, size: 6, dur: 10.2, delay: -2.1, driftX: 15, color: "emerald", opacity: 0.85 },
  { x: 74, y: 62, size: 3, dur: 7.8, delay: -4.0, driftX: -10, color: "white", opacity: 0.75 },
  { x: 78, y: 78, size: 4, dur: 13.1, delay: -6.5, driftX: 20, color: "violet", opacity: 0.65 },
  { x: 82, y: 66, size: 5, dur: 9.8, delay: -1.8, driftX: -12, color: "emerald", opacity: 0.75 },
  { x: 85, y: 54, size: 2, dur: 8.0, delay: -3.0, driftX: 8, color: "white", opacity: 0.6 },
  { x: 88, y: 74, size: 4, dur: 11.0, delay: -7.2, driftX: -18, color: "violet", opacity: 0.7 },
  { x: 55, y: 82, size: 3, dur: 10.5, delay: -4.5, driftX: 10, color: "emerald", opacity: 0.6 },
  { x: 61, y: 80, size: 4, dur: 9.0, delay: -2.8, driftX: -8, color: "violet", opacity: 0.65 },
  { x: 69, y: 84, size: 5, dur: 12.4, delay: -8.1, driftX: 14, color: "emerald", opacity: 0.8 },
  { x: 76, y: 75, size: 3, dur: 8.6, delay: -1.5, driftX: -15, color: "white", opacity: 0.7 },
  { x: 80, y: 85, size: 4, dur: 10.8, delay: -5.9, driftX: 16, color: "violet", opacity: 0.6 },
  { x: 84, y: 82, size: 3, dur: 7.5, delay: -3.7, driftX: -10, color: "emerald", opacity: 0.7 },
  { x: 91, y: 68, size: 5, dur: 13.0, delay: -9.0, driftX: 12, color: "white", opacity: 0.75 },
  { x: 48, y: 68, size: 3, dur: 9.5, delay: -0.5, driftX: -12, color: "emerald", opacity: 0.55 },
  { x: 65, y: 60, size: 2, dur: 8.2, delay: -4.8, driftX: 8, color: "violet", opacity: 0.6 },
  { x: 73, y: 52, size: 4, dur: 11.2, delay: -6.2, driftX: -14, color: "emerald", opacity: 0.7 },
];

// Subset of particles for the "subtle" variant (fewer, spread wider)
const SUBTLE_PARTICLES = PARTICLES.filter((_, i) => i % 3 === 0); // ~7 particles

export default function DataStreamBackground({ variant = "full", className = "" }) {
  const isSubtle = variant === "subtle";
  const particles = isSubtle ? SUBTLE_PARTICLES : PARTICLES;

  return (
    <div className={`datastream-bg ${className}`.trim()} aria-hidden="true">
      {/* Background ambient color radial orbs — full only */}
      {!isSubtle && (
        <>
          <div className="datastream-glow-left" />
          <div className="datastream-glow-right" />
        </>
      )}

      {/* Subtle tech coordinate grid on the left zone — full only */}
      {!isSubtle && <div className="datastream-tech-grid" />}

      {/* Layer 1 — Scrolling binary digits — full only */}
      {!isSubtle && (
        <div className="datastream-binary-zone">
          {BINARY_SEQUENCES.map((seq, colIdx) => (
            <div
              key={colIdx}
              className={`datastream-binary-col datastream-col-${colIdx + 1}`}
              style={{
                "--col-dur": `${22 + colIdx * 4}s`,
                "--col-delay": `${-colIdx * 3.5}s`,
              }}
            >
              <div className="datastream-binary-track">
                <span className="datastream-binary-text">
                  {seq.split("").map((digit, dIdx) => (
                    <span
                      key={`a-${dIdx}`}
                      className={`datastream-digit ${dIdx % 7 === 0 ? "digit-highlight" : ""
                        }`}
                    >
                      {digit}
                    </span>
                  ))}
                </span>
                {/* Duplicate track for seamless infinite scroll */}
                <span className="datastream-binary-text" aria-hidden="true">
                  {seq.split("").map((digit, dIdx) => (
                    <span
                      key={`b-${dIdx}`}
                      className={`datastream-digit ${dIdx % 7 === 0 ? "digit-highlight" : ""
                        }`}
                    >
                      {digit}
                    </span>
                  ))}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Layer 3 — Horizontal scan lines / light beams */}
      <div className="datastream-beams-container">
        <div className="datastream-beam datastream-beam-secondary-top" />
        <div className="datastream-beam datastream-beam-primary">
          <div className="datastream-beam-glint" />
        </div>
        <div className="datastream-beam datastream-beam-secondary-bottom" />

        {/* Subtle decorative circuit traces branching from beam — full only */}
        {!isSubtle && (
          <>
            <div className="datastream-circuit-trace datastream-circuit-1" />
            <div className="datastream-circuit-trace datastream-circuit-2" />
          </>
        )}
      </div>

      {/* Layer 2 — Animated bar-chart silhouette — full only */}
      {!isSubtle && (
        <div className="datastream-chart-cluster">
          {/* Upright bars */}
          <div className="datastream-bars-row">
            {BARS.map((bar, idx) => (
              <div
                key={`bar-${idx}`}
                className={`datastream-bar datastream-bar-${bar.accent}`}
                style={{
                  "--bar-h": `${bar.height}px`,
                  "--bar-dur": `${bar.duration}s`,
                  "--bar-delay": `${bar.delay}s`,
                }}
              >
                <div className="datastream-bar-cap" />
              </div>
            ))}
          </div>

          {/* Reflection bars mirroring downward across the baseline */}
          <div className="datastream-bars-reflection" aria-hidden="true">
            {BARS.map((bar, idx) => (
              <div
                key={`refl-${idx}`}
                className={`datastream-bar-mirror datastream-bar-${bar.accent}`}
                style={{
                  "--bar-h": `${Math.round(bar.height * 0.42)}px`,
                  "--bar-dur": `${bar.duration}s`,
                  "--bar-delay": `${bar.delay}s`,
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Layer 4 — Floating particles */}
      <div className="datastream-particles-layer">
        {particles.map((p, idx) => (
          <div
            key={`p-${idx}`}
            className={`datastream-particle datastream-particle-${p.color}`}
            style={{
              "--p-x": `${p.x}%`,
              "--p-y": `${p.y}%`,
              "--p-size": `${p.size}px`,
              "--p-dur": `${p.dur}s`,
              "--p-delay": `${p.delay}s`,
              "--p-drift-x": `${p.driftX}px`,
              "--p-op": p.opacity,
            }}
          />
        ))}
      </div>
    </div>
  );
}
