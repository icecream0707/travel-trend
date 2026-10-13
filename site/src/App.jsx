import { useEffect, useMemo, useRef, useState } from 'react'

const ROW_H = 40       // 순위 한 행의 높이(px). 스크롤 박스 높이 = ROW_H * VISIBLE_ROWS
const VISIBLE_ROWS = 20
const CLASS_NAMES = ['적음', '비슷', '많음']

const label = (r) => `${r.sido} ${r.name}`          // 같은 이름(중구, 동구…)을 시도로 구분
const fmtPct = (v) => (v == null ? '-' : `${v > 0 ? '+' : ''}${v.toFixed(1)}%`)
const fmtNum = (v) => v.toLocaleString('ko-KR')

export default function App() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [month, setMonth] = useState(null)          // 'YYYY-MM'
  const [selected, setSelected] = useState(null)    // 선택한 시군구 코드
  const [query, setQuery] = useState('')            // 검색창 입력 문자열
  const rowRefs = useRef({})                        // 코드 → 순위 행 DOM (스크롤 이동용)
  const boxRef = useRef(null)

  // 분석 결과 JSON 은 빌드 때 함께 배포된다(키가 필요한 API 는 브라우저에서 부르지 않는다).
  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/data.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`데이터를 불러오지 못했습니다 (${r.status})`))))
      .then((d) => {
        setData(d)
        setMonth(d.meta.months[d.meta.months.length - 1])   // 가장 최근 달을 기본으로
      })
      .catch((e) => setError(e.message))
  }, [])

  // 선택한 달의 순위 순으로 정렬한 목록
  const ranked = useMemo(() => {
    if (!data || !month) return []
    return [...data.regions].sort((a, b) => a.months[month].rank - b.months[month].rank)
  }, [data, month])

  const byLabel = useMemo(() => new Map((data?.regions ?? []).map((r) => [label(r), r.code])), [data])
  const region = data?.regions.find((r) => r.code === selected)

  // 선택하면 스크롤 박스를 그 행으로 옮긴다(별도 UI 없이 순위 위치를 보여 주는 방식).
  useEffect(() => {
    const row = rowRefs.current[selected]
    const box = boxRef.current
    if (row && box) box.scrollTop = row.offsetTop - box.clientHeight / 2 + ROW_H / 2   // 애니메이션 없이 즉시(숨은 탭에서도 동작)
  }, [selected, month])

  // 검색창 입력이 목록의 항목과 정확히 일치하면 그 시군구를 선택한다.
  const onQuery = (v) => {
    setQuery(v)
    const code = byLabel.get(v)
    if (code) setSelected(code)
  }

  if (error) return <p className="msg">{error}</p>
  if (!data) return <p className="msg">불러오는 중…</p>

  const m = region?.months[month]
  return (
    <main>
      <h1>지역 관광 트렌드</h1>
      <p className="sub">
        시군구의 전년 동월대비 방문수요 변화율과, 같은 달 날씨(강수) 변화와의 관련 가능성을 보여 줍니다.
      </p>

      <div className="controls">
        <label>
          기준 월
          <select value={month} onChange={(e) => setMonth(e.target.value)}>
            {[...data.meta.months].reverse().map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
        </label>
        <label>
          시군구 검색
          <input list="regions" value={query} placeholder="예: 경기 가평군"
                 onChange={(e) => onQuery(e.target.value)} />
          <datalist id="regions">
            {data.regions.map((r) => <option key={r.code} value={label(r)} />)}
          </datalist>
        </label>
      </div>

      <section className="grid">
        <div>
          <h2>{month} 전년 동월대비 변화율 순위</h2>
          <p className="note">
            방문수요 상위 80%의 시군구 {data.meta.rankedCount}곳만 나열했습니다
            (하위 20% {data.meta.excludedCount}곳은 방문자가 적어 변화율이 크게 흔들려 제외).
          </p>
          <ol className="rank" ref={boxRef} style={{ height: ROW_H * VISIBLE_ROWS }}>
            {ranked.map((r) => {
              const x = r.months[month]
              return (
                <li key={r.code} ref={(el) => (rowRefs.current[r.code] = el)}
                    className={r.code === selected ? 'on' : ''} style={{ height: ROW_H }}
                    onClick={() => { setSelected(r.code); setQuery(label(r)) }}>
                  <span className="no">{x.rank}</span>
                  <span className="nm">{label(r)}</span>
                  <span className={`pct ${x.yoy >= 0 ? 'up' : 'down'}`}>{fmtPct(x.yoy)}</span>
                  {x.alert && <span className="badge">날씨 관련 가능성</span>}
                  {!r.station && <span className="badge gray">날씨 판단 불가</span>}
                </li>
              )
            })}
          </ol>
        </div>

        <div>
          {!region ? (
            <p className="msg">시군구를 검색하거나 목록에서 선택하세요.</p>
          ) : (
            <Detail region={region} month={month} m={m} months={data.meta.months} baseline={data.meta.baseline} />
          )}
        </div>
      </section>

      <footer>
        방문수요: 한국관광공사 데이터랩(외지인+외국인, 월 합산) · 날씨: 기상청 ASOS · 평년 {data.meta.baseline}.
        날씨 변화는 방문수요 변화에 영향을 미쳤을 가능성만 보여 주며 인과를 증명하지 않습니다.
        분석 {data.meta.generatedAt}
      </footer>
    </main>
  )
}

// 선택한 시군구의 상세: 해석 문구, 수치, 12개월 변화율 추이, 날씨 비교
function Detail({ region, month, m, months, baseline }) {
  return (
    <div className="detail">
      <h2>{label(region)}</h2>
      <p className="text">{m.text}</p>

      <dl>
        <div><dt>{month} 방문수요</dt><dd>{fmtNum(m.v)}명</dd></div>
        <div><dt>전년 동월</dt><dd>{fmtNum(m.pv)}명</dd></div>
        <div><dt>변화율</dt><dd>{fmtPct(m.yoy)}</dd></div>
      </dl>

      <h3>월별 전년 동월대비 변화율</h3>
      <Trend region={region} months={months} current={month} />

      <h3>날씨 변화 (평년 {baseline} 3분위 기준)</h3>
      {region.station ? (
        m.w ? (
          <table>
            <thead><tr><th>속성</th><th>전년</th><th>올해</th><th>평년 중간 범위</th><th>판정</th></tr></thead>
            <tbody>
              {[['rainDays', '강수일수', '일'], ['rainMm', '월강수량', 'mm']].map(([k, name, unit]) => {
                const a = m.w[k]
                return (
                  <tr key={k} className={a.alert ? 'alert' : ''}>
                    <td>{name}</td>
                    <td>{a.prev}{unit} ({CLASS_NAMES[a.prevClass]})</td>
                    <td>{a.cur}{unit} ({CLASS_NAMES[a.curClass]})</td>
                    <td>{a.lo}~{a.hi}{unit}</td>
                    <td>{a.alert ? '확연한 변화' : '-'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : <p className="note">이 달은 날씨 자료가 부족해 날씨 판단 불가입니다.</p>
      ) : <p className="note">이 시군구에는 ASOS 관측소가 없어 날씨 판단 불가입니다.</p>}
      {region.station && <p className="note">관측소: {region.station.name} ({region.station.id}) — 시군구 전체가 아닌 관측소 한 지점의 값입니다.</p>}
    </div>
  )
}

// 12개월 변화율 막대 그래프(차트 라이브러리 없이 SVG). 선택 월은 진하게.
function Trend({ region, months, current }) {
  const vals = months.map((k) => region.months[k].yoy ?? 0)
  const max = Math.max(5, ...vals.map(Math.abs))          // 0 기준선 위/아래 대칭 범위
  const W = 480, H = 140, mid = H / 2, bw = W / months.length
  return (
    <svg viewBox={`0 0 ${W} ${H + 18}`} className="trend" role="img" aria-label="월별 변화율 막대 그래프">
      <line x1="0" x2={W} y1={mid} y2={mid} stroke="currentColor" opacity=".3" />
      {months.map((k, i) => {
        const h = (Math.abs(vals[i]) / max) * (mid - 6)
        return (
          <g key={k}>
            <rect x={i * bw + 4} width={bw - 8} y={vals[i] >= 0 ? mid - h : mid} height={Math.max(h, 1)}
                  className={vals[i] >= 0 ? 'bar up' : 'bar down'} opacity={k === current ? 1 : 0.45}>
              <title>{k}: {fmtPct(region.months[k].yoy)}</title>
            </rect>
            <text x={i * bw + bw / 2} y={H + 12} textAnchor="middle" fontSize="9">{k.slice(5)}</text>
          </g>
        )
      })}
    </svg>
  )
}
