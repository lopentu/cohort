import { useState } from 'react'

// Where each work outside the benchmark sits — by association across the whole
// canon first, and by distance against the benchmark's own spread second.
//
// The order is the argument, and it is the reverse of what this panel showed
// until 2026-09-06. It led with a Δ against a null band whose ceiling is the
// distance of the benchmark's *most eccentric member*, so every disputed work
// and every interloper alike came back "not distinguishable from the
// benchmark" — true, and an answer to nothing. That reading is still here,
// because knowing the band is uninformative is worth seeing, but it is no
// longer the headline.
//
// The headline is the measure with the corpus behind it: of the works nearest
// this one across the canon, are benchmark members more common than the 1.1%
// chance would give? See cohort/association.py for why that is the question
// Radich's brief actually asks.
//
// Three things are drawn rather than described, because each is what stops the
// measure being over-read:
//
//   - the calibration band — what a *known* benchmark work scores, self held
//     out. A share against chance says the overlap is not an accident; it does
//     not say the association is as strong as membership normally looks.
//   - the blind count inside it — how many undisputed members the method fails
//     to recover. A zero is not an exclusion while that number is high.
//   - the nearest work *outside* the group beside the nearest one inside it.
//     Character n-grams track subject matter, so a work surrounded by one genre
//     sits near any group heavy in that genre; the check that survives it is
//     whether the group's own member is nearer than the same material by other
//     hands.
//
// And every row carries a **verdict**, because the question has two branches
// and a row that answered only the first was a blank three times out of four.
// "No benchmark works nearby" is not an answer; "no benchmark works nearby, and
// its own nearest work stands further clear of the rest than 88% of the corpus"
// is one. `unplaced` is the honest fourth state and is drawn neutrally — a work
// the method cannot see must not look like a work shown not to belong.
export default function Placements({ data }) {
  if (!data) return null

  const rows = Object.entries(data.groups).flatMap(([, g]) => g.profiles)
  const deltas = rows.map((p) => p.mean_delta_to_benchmark)
  const lo = Math.min(data.null.min, ...deltas)
  const hi = Math.max(data.null.max, ...deltas)
  const pad = (hi - lo) * 0.12 || 0.05
  const domain = [lo - pad, hi + pad]

  const cal = (data.calibration || []).find((c) => c.k === 25)

  return (
    <section className="study">
      <h2>Where the works in doubt sit</h2>
      <p className="hint small">
        Every catalogued work outside the benchmark, measured the same way. Not
        what any agent proposed — the standing measurement their hypotheses are
        read against.
      </p>

      {cal && (
        <p className="study-calibration">
          <strong>How to read a share.</strong> A known {data.benchmark_label} work,
          scored with itself held out, has {pctf(cal.min)}–{pctf(cal.max)} of
          its 25 nearest neighbours in {data.benchmark_label} (median{' '}
          {pctf(cal.median)}), against {pctf(data.groups && expected(data))} by
          chance. <strong>{cal.blind} of {cal.n}</strong> undisputed members
          score zero — so a work with no enrichment has not been shown to be an
          outsider, only to be somewhere this method cannot see it.
        </p>
      )}

      {/* Carried in the payload rather than written here, so it cannot be
          dropped by a renderer that finds it inconvenient. */}
      <p className="study-caveat">{data.caveat}</p>

      {Object.entries(data.groups).map(([label, group]) => (
        <div className="study-group" key={label}>
          <h3>{label}<span className="study-n">{group.profiles.length}</span></h3>

          {group.profiles.map((p) => (
            <Work key={p.work} profile={p} domain={domain} band={data.null}
                  benchmark={data.benchmark_label} />
          ))}

          {group.unmeasurable.length > 0 && (
            <p className="study-unmeasurable">
              <strong>Not profiled:</strong> {group.unmeasurable.join(', ')} — below the
              character floor. This method has nothing to say about them, which is a
              result rather than a gap.
            </p>
          )}
        </div>
      ))}
    </section>
  )
}

function expected(data) {
  const any = Object.values(data.groups).flatMap((g) => g.profiles)[0]
  return any?.association?.expected_share ?? 0
}

function Work({ profile, domain, band, benchmark }) {
  const [open, setOpen] = useState(false)
  const a = profile.association
  const e = a?.enrichment?.[0]
  const at = (v) => ((v - domain[0]) / (domain[1] - domain[0])) * 100

  //: The server decides the verdict, not this component. It is recorded in the
  //: payload of every association written to the graph, and a browser that
  //: re-derived it could disagree with what the record says.
  const v = a?.verdict || ''

  return (
    <div className={`study-work v-${v}`}>
      <button className="study-head" onClick={() => setOpen(!open)}>
        <span className="study-id">{profile.work}</span>
        {v && <span className={`assoc-verdict v-${v}`}>{VERDICT[v]}</span>}

        {e ? (
          <>
            <span className="assoc-scale" role="img"
                  aria-label={`${e.hits} of ${e.k} nearest are ${benchmark}; known members reach ${pctf(e.calibration_min)} to ${pctf(e.calibration_max)}`}>
              <span className="cal-band"
                    style={{ left: `${shareAt(e.calibration_min)}%`,
                             width: `${shareAt(e.calibration_max) - shareAt(e.calibration_min)}%` }} />
              <span className="cal-median" style={{ left: `${shareAt(e.calibration_median)}%` }} />
              <span className="cal-mark" style={{ left: `${shareAt(e.share)}%` }} />
            </span>
            <span className="assoc-figure">
              <strong>{e.hits}/{e.k}</strong>
              <em>{e.p_value < 1 ? `p=${fmtp(e.p_value)}` : ''}</em>
            </span>
          </>
        ) : (
          <span className="hint small">no association measured</span>
        )}
      </button>

      {/* Two branches, two paragraphs. Run together they read as one hedge;
          apart, the first says whether it belongs and the second says where it
          sits, and the second is the one with something to say when the first
          comes back empty. */}
      {a && (
        <div className="study-readings">
          <p className="study-reading">{a.group_reading}</p>
          {a.neighbourhood && (
            <p className={`study-reading hood ${a.neighbourhood.dominant ? 'lead' : ''}`}>
              {a.neighbourhood.reading}
            </p>
          )}
        </div>
      )}

      {/* The genre control, on the row. Two numbers: the nearest benchmark work
          and the nearest work that is not one. */}
      {a?.nearest_in_group && a?.nearest_outside_group && (
        <p className="assoc-control">
          nearest {benchmark}: <code>{a.nearest_in_group.work}</code> Δ{' '}
          {a.nearest_in_group.delta} <span className="rank">rank {a.nearest_in_group.rank}</span>
          <span className="sep" />
          nearest outside: <code>{a.nearest_outside_group.work}</code> Δ{' '}
          {a.nearest_outside_group.delta}{' '}
          <span className="rank">rank {a.nearest_outside_group.rank}</span>
        </p>
      )}

      {open && (
        <div className="study-neighbours">
          <h4>Nearest in the corpus</h4>
          <ol>
            {(a?.neighbours || profile.neighbours).map((n) => (
              <li key={n.work}>
                <span className="nb-rank">{n.rank ?? ''}</span>
                <span className={`nb-work${n.label === benchmark ? ' nb-bench' : ''}`}>
                  {n.work}
                </span>
                {n.label && <span className="nb-label">{n.label}</span>}
                <span className="nb-delta">Δ {n.delta}</span>
              </li>
            ))}
          </ol>
          <p className="hint small">
            Nearest by the same measure, over the whole corpus rather than the
            catalogue — a work can only be associated with another reference point
            if that reference point is in the space.
          </p>

          {/* The band, kept and demoted. Its ceiling is the distance of the
              benchmark's most eccentric member, so almost nothing falls
              outside it — which is why it is no longer the headline, and why
              it is still worth showing that it says nothing here. */}
          <h4>Distance against the benchmark&apos;s own spread</h4>
          <div className="band-row">
            <span className="study-scale" role="img"
                  aria-label={`delta ${profile.mean_delta_to_benchmark}, benchmark band ${band.min} to ${band.max}`}>
              <span className="scale-band"
                    style={{ left: `${at(band.min)}%`, width: `${at(band.max) - at(band.min)}%` }} />
              <span className="scale-median" style={{ left: `${at(band.median)}%` }} />
              <span className="scale-mark" style={{ left: `${at(profile.mean_delta_to_benchmark)}%` }} />
            </span>
            <span className="study-delta">Δ {profile.mean_delta_to_benchmark}</span>
          </div>
          <p className="hint small">
            {profile.reading}. The band runs to the benchmark&apos;s most distant
            member, so it is a check against over-reading a small distance rather
            than a test anything is likely to fail.
          </p>
        </div>
      )}
    </div>
  )
}

//: What each verdict is called on screen. Short, because the chip sits in a
//: fixed 6.5rem column of a row whose scales have to line up between works —
//: and because the paragraph immediately below says the whole thing. "alternate
//: reference point" became "alternate" for that reason, not because the
//: shorter word says as much.
//:
//: The words are still chosen so none can be read as an exclusion: `not
//: placed` says the method placed the work nowhere, which is what happened,
//: and not that the work does not belong.
const VERDICT = {
  associates: 'associates',
  weak: 'weak',
  alternate: 'alternate',
  unplaced: 'not placed',
}

//: Shares are drawn on a fixed 0–30% scale rather than one fitted to the data.
//: A fitted axis would rescale when a new work arrives and make two screenshots
//: of the same finding disagree.
const SHARE_MAX = 0.3
function shareAt(x) {
  return Math.max(0, Math.min(100, (x / SHARE_MAX) * 100))
}

function pctf(x) {
  return `${Math.round((x || 0) * 1000) / 10}%`
}

//: One significant figure and never rounded to zero — a p-value shown as "0"
//: claims a certainty no finite test has.
function fmtp(p) {
  if (p >= 0.001) return p.toFixed(3)
  const e = p.toExponential(0)
  return e.replace('e', '×10^').replace('-', '−')
}
