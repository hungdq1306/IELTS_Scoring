function Frog({ size = 100, className = "" }) {
  return <svg className={`frog ${className}`} width={size} height={size * 0.85} viewBox="0 0 160 136" fill="none" aria-hidden="true">
    <ellipse cx="80" cy="119" rx="68" ry="13" fill="#b8d7b7" />
    <path d="M20 120c23-16 71-17 119 0-45 12-88 12-119 0Z" fill="#7fa581" />
    <path d="M48 95c-9 15-9 24 2 25h60c11-1 11-12 2-25" fill="#9cce85" stroke="#315d48" strokeWidth="3" />
    <path d="M31 68c-3-15 1-33 13-40 13-9 26 0 30 8h12c5-11 20-16 30-8 12 9 14 27 11 40 14 30-8 43-47 43S17 98 31 68Z" fill="#b8df99" stroke="#315d48" strokeWidth="3" />
    <ellipse cx="53" cy="47" rx="5" ry="7" fill="#213e33" /><ellipse cx="107" cy="47" rx="5" ry="7" fill="#213e33" />
    <ellipse cx="43" cy="73" rx="10" ry="6" fill="#efb69f" /><ellipse cx="117" cy="73" rx="10" ry="6" fill="#efb69f" />
    <path d="M67 70q13 14 26 0" stroke="#315d48" strokeWidth="3" strokeLinecap="round" />
    <path d="m115 110 19-48 8 3-19 48-8 5v-8Z" fill="#f4c48d" stroke="#8c673e" strokeWidth="2" />
    <path d="M55 102q-8 9 2 16m46-16q8 9-2 16" stroke="#315d48" strokeWidth="3" strokeLinecap="round" />
  </svg>;
}
function Brand() {
  return <span className="brand"><Frog size={44} /><span>FogWrite<small>IELTS Writing Studio</small></span></span>;
}
export {
  Brand,
  Frog
};
