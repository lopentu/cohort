import { useState } from 'react'

// Where each disputed work sits, against the spread of the works nobody
// disputes.
//
// The scale is the argument. A Δ on its own is a number nobody can read; the
// same Δ drawn against the band the benchmark's own members occupy is
// immediately legible as "no further out than the yardstick's own variation".
// Twice on 2026-09-06 an apparent separation here turned out to be an
// artifact, and both would have been obvious at a glance against this band —
// so the band is drawn first and every marker sits on top of it, rather than
// the distance being shown alone with the calibration a click away.
//
// One shared domain across every row, so two works can be compared by eye.
//
// Takes its data as a prop and fetches nothing. This was a tab of its own
// until 2026-09-06, which put a standing measurement over the catalogue on a
// different page from the hypotheses it bears on — so a reader had to hold
// one in their head while looking at the other. It is a section of Findings
// now, and the owner of the fetch is the page.
export default function Placements({ data }) {
  if (!data) return null

  const rows = Object.entries(data.groups).flatMap(([, g]) => g.profiles)
  const deltas = rows.map((p) => p.mean_delta_to_benchmark)
  const lo = Math.min(data.null.min, ...deltas)
  const hi = Math.max(data.null.max, ...deltas)
  const pad = (hi - lo) * 0.12 || 0.05
  const domain = [lo - pad, hi + pad]

  return (
    <section className="study">
      <h2>Where the works in doubt sit</h2>
      <p className="hint small">
        Every catalogued work outside the benchmark, measured the same way —
        this is not what any agent proposed, it is the standing measurement
        their hypotheses are read against.
      </p>

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

function Work({ profile, domain, band, benchmark }) {
  const [open, setOpen] = useState(false)
  const at = (v) => ((v - domain[0]) / (domain[1] - domain[0])) * 100

  return (
    <div className={`study-work ${profile.inside_null ? 'inside' : 'outside'}`}>
      <button className="study-head" onClick={() => setOpen(!open)}>
        <span className="study-id">{profile.work}</span>

        <span className="study-scale" role="img"
              aria-label={`delta ${profile.mean_delta_to_benchmark}, benchmark band ${band.min} to ${band.max}`}>
          <span className="scale-band"
                style={{ left: `${at(band.min)}%`, width: `${at(band.max) - at(band.min)}%` }} />
          <span className="scale-median" style={{ left: `${at(band.median)}%` }} />
          <span className="scale-mark" style={{ left: `${at(profile.mean_delta_to_benchmark)}%` }} />
        </span>

        <span className="study-delta">Δ {profile.mean_delta_to_benchmark}</span>
      </button>

      <p className="study-reading">{profile.reading}</p>

      {open && (
        <div className="study-neighbours">
          <h4>Nearest in the corpus</h4>
          <ol>
            {profile.neighbours.map((n) => (
              <li key={n.work}>
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
        </div>
      )}
    </div>
  )
}
