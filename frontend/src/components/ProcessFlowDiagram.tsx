import type { Params } from "../api/client";
import type { KeyboardEvent } from "react";

const stages = [
  { id: "inlet", label: "Raw influent", x: 20 },
  { id: "1", label: "Anoxic 1", x: 200 },
  { id: "2", label: "Anoxic 2", x: 400 },
  { id: "3", label: "Aerobic 1", x: 600 },
  { id: "4", label: "Aerobic 2", x: 800 },
  { id: "5", label: "Aerobic 3", x: 1000 },
  { id: "sst", label: "SST", x: 1210 },
];

function Pipe({ d, sludge = false }: { d: string; sludge?: boolean }) {
  return <g fill="none" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} stroke={sludge ? "#633782" : "#17628e"} strokeWidth="13" />
    <path d={d} stroke={sludge ? "#ad73cd" : "#39b7ec"} strokeWidth="9" />
    <path d={d} stroke={sludge ? "#e5c3f5" : "#b6edff"} strokeWidth="2" transform="translate(0 -2)" />
  </g>;
}

function Tank({ aerobic }: { aerobic: boolean }) {
  return <g>
    <ellipse cx="77" cy="192" rx="88" ry="15" fill="#dce5d2" />
    <path d="M 8 168 L 32 64 H 150 L 169 168 Z" fill="#e9e6d9" stroke="#8f968b" strokeWidth="2" />
    <path d="M 8 168 H 169 V 190 H 8 Z" fill="url(#mle-concrete)" stroke="#959c92" />
    <path d="M 169 168 L 150 64 V 87 L 169 190 Z" fill="#a9aea0" />
    <path d="M 22 162 L 42 77 H 141 L 155 162 Z" fill={aerobic ? "url(#mle-water)" : "url(#mle-anoxic)"} stroke="#526d6e" strokeWidth="3" />
    {[105, 129, 150].map(y => <path key={y} d={`M 40 ${y} Q 66 ${y - 9} 88 ${y} T 143 ${y}`} fill="none" stroke="#e0f4eb" opacity=".4" strokeWidth="2" />)}
    {aerobic ? <g>
      {[45, 72, 99, 126].map((x, column) => <g key={x}>
        <path d={`M ${x} 153 V 164`} stroke="#374f5d" strokeWidth="4" />
        {Array.from({ length: 9 }, (_, i) => <circle key={i} cx={x + Math.sin(i * 3 + column) * 6} cy={145 - i * 7} r={1.5 + (i % 3) * .6} fill="#e5fbff" opacity={.5 + (i % 3) * .2} />)}
      </g>)}
      <path d="M 42 165 H 138" stroke="#69818c" strokeWidth="3" />
    </g> : <g>
      <ellipse cx="89" cy="139" rx="34" ry="12" fill="none" stroke="#d4dec0" strokeWidth="2" />
      <ellipse cx="89" cy="139" rx="23" ry="8" fill="none" stroke="#d4dec0" />
      <path d="M 89 68 V 137 M 68 132 L 108 145 M 71 147 L 106 131" stroke="#334b51" strokeWidth="7" strokeLinecap="round" />
      <path d="M 89 68 V 136 M 68 131 L 108 144 M 71 146 L 106 130" stroke="#c9d4cf" strokeWidth="3" />
    </g>}
    <path d="M 32 70 H 150 L 143 56 H 38 Z" fill="#818f88" stroke="#526562" />
    <g fill="none" stroke="#d5a531" strokeWidth="2">
      <path d="M 37 57 V 39 H 146 V 57 M 37 47 H 146" />
      {[50, 78, 106, 134].map(x => <path key={x} d={`M ${x} 39 V 59`} />)}
    </g>
    <rect x="81" y="35" width="14" height="28" rx="4" fill="url(#mle-water)" stroke="#27556d" />
    <path d="M 84 39 V 56" stroke="#c3eaff" strokeWidth="2" />
  </g>;
}

export function ProcessFlowDiagram({ parameters, selected, onSelect }: {
  parameters: Params; selected: string; onSelect: (id: string) => void;
}) {
  const interaction = (id: string, label: string) => ({
    role: "button", tabIndex: 0, "aria-label": label, "aria-pressed": selected === id,
    className: `plant-target ${selected === id ? "is-selected" : ""}`,
    onClick: () => onSelect(id),
    onKeyDown: (event: KeyboardEvent<SVGGElement>) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(id); }
    },
  });
  return <svg className="plant-diagram" viewBox="0 0 1580 435" aria-label="Interactive MLE treatment plant with two anoxic tanks, three aerated tanks, clarifier and recycle pipes">
    <defs>
      <linearGradient id="mle-water" x2="0" y2="1"><stop stopColor="#236788" /><stop offset="1" stopColor="#8dddf3" /></linearGradient>
      <linearGradient id="mle-anoxic" x2="0" y2="1"><stop stopColor="#526f65" /><stop offset="1" stopColor="#a3b391" /></linearGradient>
      <linearGradient id="mle-concrete" x2="0" y2="1"><stop stopColor="#e4e1d3" /><stop offset="1" stopColor="#b9bdad" /></linearGradient>
    </defs>
    <path d="M 22 182 Q 90 132 190 167 H 1430 Q 1485 181 1500 219 Q 1460 242 1390 223 H 130 Q 45 223 22 182" fill="#eef2e6" />
    <Pipe d="M 112 127 H 1535" />
    <Pipe d="M 1193 127 V 309 Q 1193 325 1177 325 H 184 Q 169 325 169 310 V 127" />
    <Pipe d="M 1320 222 V 389 H 148 Q 136 389 136 377 V 127" sludge />
    <Pipe d="M 1320 389 V 422" sludge />
    {[178, 380, 580, 780, 980, 1180, 1450, 1540].map(x => <path key={x} d={`M ${x - 9} 117 L ${x + 7} 127 L ${x - 9} 137 Z`} fill="#1688bd" stroke="#155f88" />)}
    <path d="M 550 317 L 536 325 L 550 333 M 545 381 L 531 389 L 545 397 M 1312 415 L 1320 429 L 1328 415" fill="#8354a4" stroke="#633782" />
    {stages.map(stage => <g key={stage.id} transform={`translate(${stage.x} 0)`} {...interaction(stage.id, `Edit ${stage.label} parameters`)}>
      <rect className="plant-hit" x="-4" y="24" width={stage.id === "sst" ? 212 : 180} height="255" rx="16" />
      {stage.id === "inlet" ? <g>
        <path d="M 0 160 L 32 87 H 115 L 95 160 Z" fill="url(#mle-water)" stroke="#8f998e" strokeWidth="8" />
        <path d="M 0 160 V 180 H 95 V 160 M 115 87 V 109" fill="#c4c8b8" stroke="#929b90" strokeWidth="3" />
        {[0, 1, 2, 3].map(i => <path key={i} d={`M ${12 + i * 4} ${151 - i * 13} Q 50 ${164 - i * 13} ${97 + i * 3} ${151 - i * 13}`} fill="none" stroke="#d6f9ff" strokeWidth="2" />)}
        <path d="M 33 90 V 64 H 114 V 90 M 33 75 H 114 M 57 65 V 87 M 88 65 V 87" stroke="#72817c" strokeWidth="3" fill="none" />
      </g> : stage.id === "sst" ? <g>
        <path d="M 17 151 L 30 196 L 110 235 L 190 196 L 202 151" fill="url(#mle-concrete)" stroke="#929c91" strokeWidth="2" />
        <path d="M 38 176 V 226 M 181 176 V 226" stroke="#89948a" strokeWidth="9" />
        <ellipse cx="110" cy="132" rx="100" ry="48" fill="#e3e0ce" stroke="#9caa97" strokeWidth="3" />
        <ellipse cx="110" cy="130" rx="91" ry="39" fill="url(#mle-water)" />
        <ellipse cx="110" cy="133" rx="70" ry="26" fill="none" stroke="#b9ebee" strokeWidth="2" />
        <ellipse cx="110" cy="134" rx="17" ry="9" fill="#4f7175" />
        <path d="M 110 134 V 80" stroke="#74847d" strokeWidth="9" />
        <path d="M 106 120 L 195 150 L 195 138 L 106 108 Z" fill="#bac4b1" stroke="#788b7d" />
        <path d="M 107 105 V 89 L 197 120 V 139 M 108 98 L 196 130 M 137 100 V 121 M 166 110 V 132" stroke="#d2a12d" strokeWidth="2" fill="none" />
        <path d="M 20 117 V 99 Q 110 35 201 99 V 117" fill="none" stroke="#d2a12d" strokeWidth="3" />
        <text x="110" y="37" className="plant-name">Secondary clarifier</text>
      </g> : <Tank aerobic={Number(stage.id) >= 3} />}
      <text x={stage.id === "sst" ? 110 : 85} y="246" className="plant-name">{stage.label === "SST" ? "RAS / WAS" : stage.label}</text>
      <text x={stage.id === "sst" ? 110 : 85} y="266" className="plant-detail">{Number(stage.id) > 0 ? `${parameters[`tank${stage.id}_volume_m3` as keyof Params].toFixed(1)} m³ / lane` : "Excel time series"}</text>
      {Number(stage.id) >= 3 && <text x="85" y="285" className="plant-detail">Airflow: Excel time series</text>}
    </g>)}
    <g transform="translate(1460 0)">
      <path d="M 0 146 L 12 101 H 63 L 78 146 Z" fill="url(#mle-water)" stroke="#a3ad9e" strokeWidth="6" />
      <path d="M 5 143 Q 39 154 74 143 M 10 132 Q 39 141 69 132" fill="none" stroke="#e1faff" strokeWidth="2" />
      <text x="43" y="83" className="plant-name">Final effluent</text>
    </g>
    <g {...interaction("mlr", "Edit internal recycle ratio")}>
      <rect className="plant-badge" x="624" y="307" width="272" height="36" rx="10" />
      <text x="760" y="331" className="plant-name">← MLR · {parameters.mlr_ratio} × Q</text>
    </g>
    <g {...interaction("sst", "Edit return and waste sludge time series")}>
      <rect className="plant-badge sludge-badge" x="595" y="371" width="330" height="36" rx="10" />
      <text x="760" y="395" className="plant-name">← Return activated sludge (RAS)</text>
    </g>
    <text x="1360" y="425" className="plant-name">WAS</text>
  </svg>;
}
