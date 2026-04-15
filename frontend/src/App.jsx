import React, { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const SPECIES_COLORS = ["#0ea5e9", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"];

const API_URL = process.env.REACT_APP_API_URL || 'https://pidgey-ai-backend-836832472845.us-central1.run.app';

export default function App() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const suggestions = [
    "Best park for birding this weekend?",
    "What birds can I see in Prospect Park?",
    "Is this Saturday or Sunday better for birding?",
    "Any rare birds spotted in Upper Manhattan?",
    "Where can I see a Bald Eagle in NYC?",
    "Which park has the most warblers?"
  ];

  const favoriteParks = [
    "Central Park — The Ramble",
    "Inwood Hill Park",
    "Fort Tryon Park",
    "Morningside Park",
    "Central Park — Reservoir",
    "Prospect Park",
    "Green-Wood Cemetery",
    "Bryant Park"
  ];

  const analyze = async (q) => {
    const question = q || query;
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: question })
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: 24, fontFamily: 'sans-serif' }}>
      <h1 style={{ fontSize: 32, marginBottom: 4 }}>🐦 Pidgey AI</h1>
      <p style={{ color: '#666', marginBottom: 24 }}>
        NYC's Bird Expert: Find the best birding spots across New York City this weekend!
      </p>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
        {suggestions.map(s => (
          <button key={s} onClick={() => { setQuery(s); analyze(s); }}
            style={{ padding: '6px 12px', borderRadius: 20, border: '1px solid #0ea5e9',
                     background: 'white', color: '#0ea5e9', cursor: 'pointer', fontSize: 13 }}>
            {s}
          </button>
        ))}
      </div>

      <div style={{ background: '#f1f5f9', borderRadius: 12, padding: 12, marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: '#475569', marginBottom: 8, fontWeight: 600 }}>
          📍 Our Favorite NYC Spots
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {favoriteParks.map(p => (
            <button key={p} onClick={() => setQuery(`What birds can I see at ${p}?`)}
              style={{ padding: '4px 10px', borderRadius: 16, border: '1px solid #cbd5e1',
                       background: 'white', color: '#334155', cursor: 'pointer', fontSize: 12 }}>
              {p}
            </button>
          ))}
        </div>
        <div style={{ fontSize: 11, color: '#64748b', marginTop: 8 }}>
          We cover 8 top NYC birding hotspots — 30 days of real eBird data across Manhattan and Brooklyn
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        <input value={query} onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && analyze()}
          placeholder="Ask about birding in Manhattan..."
          style={{ flex: 1, padding: '10px 14px', borderRadius: 8,
                   border: '1px solid #ddd', fontSize: 15 }} />
        <button onClick={() => analyze()}
          style={{ padding: '10px 20px', borderRadius: 8, background: '#0ea5e9',
                   color: 'white', border: 'none', cursor: 'pointer', fontSize: 15 }}>
          {loading ? '...' : 'Analyze'}
        </button>
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: '#666' }}>
          🔍 Fetching real-time eBird data and analyzing...
        </div>
      )}

      {error && (
        <div style={{ padding: 16, background: '#fee2e2', borderRadius: 8, color: '#dc2626' }}>
          Error: {error}
        </div>
      )}

      {result && (() => {
        const rt = result.response_type;
        const isSpecies = rt === "specific_park" || rt === "species_list";
        const isSpecificPark = rt === "specific_park";
        const isSpeciesList = rt === "species_list";
        const isWeather = rt === "weather";
        const isSpeciesSearch = rt === "species_search";
        const isOffTopic = rt === "off_topic";
        const isFull = rt === "recommendation" || rt === "comparison" || (!rt && result.top_park);
        const searchResults = result.species_search_results;
        const searchChartData = (searchResults?.found_in_parks || []).map(p => ({
          park: p.park, sighting_count: p.sighting_count
        }));
        if (isOffTopic) {
          return (
            <div>
              <div style={{
                padding: 20,
                background: '#eff6ff',
                border: '2px solid #3b82f6',
                borderRadius: 12,
                marginBottom: 16,
                color: '#1e3a8a',
                fontSize: 16,
                lineHeight: 1.7,
                whiteSpace: 'pre-wrap'
              }}>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>🐦 Pidgey AI</div>
                {result.direct_answer}
              </div>
              <div style={{ fontSize: 13, color: '#475569', marginBottom: 8 }}>
                Try one of these:
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {suggestions.slice(0, 4).map(s => (
                  <button key={s} onClick={() => { setQuery(s); analyze(s); }}
                    style={{ padding: '6px 12px', borderRadius: 20, border: '1px solid #3b82f6',
                             background: 'white', color: '#1d4ed8', cursor: 'pointer', fontSize: 13 }}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          );
        }
        return (
        <div>
          {result.direct_answer && (
            <div style={{
              padding: 20,
              background: "#f0fdf4",
              borderRadius: 12,
              marginBottom: 16,
              borderLeft: "4px solid #16a34a"
            }}>
              <h3 style={{ margin: "0 0 8px", color: "#15803d" }}>
                💬 Answer
              </h3>
              <p style={{ margin: 0, fontSize: 16, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                {result.direct_answer}
              </p>
            </div>
          )}

          {result.weather_note && result.weather_note.length > 0 && (
            <div style={{
              padding: 16,
              background: "#fefce8",
              borderRadius: 12,
              marginBottom: 16,
              borderLeft: "4px solid #eab308"
            }}>
              <strong>🌤️ Best Time to Go:</strong>
              <div style={{ margin: "8px 0 0", lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                {result.weather_note}
              </div>
            </div>
          )}

          {result.week_forecast_table?.length > 0 && (() => {
            const qualityColor = {
              Excellent: { bg: '#dcfce7', fg: '#166534' },
              Good:      { bg: '#f0fdf4', fg: '#15803d' },
              Fair:      { bg: '#fefce8', fg: '#854d0e' },
              Poor:      { bg: '#fee2e2', fg: '#b91c1c' },
            };
            const rows = result.week_forecast_table;
            const dateFiltered = rows.length < 10;
            const header = dateFiltered && rows.length > 0
              ? `Forecast for ${rows[0].day} — ${rows[rows.length - 1].day}`
              : '16-Day Birding Forecast';
            return (
              <div style={{ marginBottom: 24 }}>
                <h3 style={{ marginBottom: 12 }}>{header}</h3>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                  <thead>
                    <tr style={{ background: '#f1f5f9' }}>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>Date</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>Temp</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>Conditions</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left' }}>Birding Quality</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map(d => {
                      const c = qualityColor[d.quality] || qualityColor.Good;
                      return (
                        <tr key={d.date} style={{ borderBottom: '1px solid #e2e8f0' }}>
                          <td style={{ padding: '8px 12px' }}>{d.day}</td>
                          <td style={{ padding: '8px 12px' }}>{d.temp}°F</td>
                          <td style={{ padding: '8px 12px' }}>{d.forecast}</td>
                          <td style={{ padding: '8px 12px' }}>
                            <span style={{
                              background: c.bg, color: c.fg,
                              padding: '2px 10px', borderRadius: 12,
                              fontSize: 12, fontWeight: 600,
                            }}>
                              {d.quality}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <p style={{ fontSize: 11, color: '#94a3b8', marginTop: 8 }}>
                  Powered by Open-Meteo • 16-day forecast
                </p>
              </div>
            );
          })()}

          {!result.top_park && result.reason && (
            <div style={{ padding: 16, background: '#f1f5f9', borderRadius: 12, marginBottom: 16, lineHeight: 1.6 }}>
              {result.reason}
            </div>
          )}

          {isSpeciesSearch && searchResults?.is_generic_type && searchResults?.grouped_chart_data?.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h3>{`Top ${searchResults?.top_species_names?.length || 5} ${searchResults?.searched_species} Species by Birds Counted — Last 30 Days`}</h3>
              <ResponsiveContainer width="100%" height={350}>
                <BarChart data={searchResults.grouped_chart_data}
                  margin={{ top: 5, right: 30, left: 120, bottom: 60 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="park"
                    tick={{ fontSize: 11, fill: "#000" }}
                    angle={-35}
                    textAnchor="end"
                    interval={0}
                  />
                  <YAxis
                    tick={{ fill: "#000" }}
                    label={{ value: "Counts", angle: -90, position: "insideLeft", textAnchor: "middle", dy: 30, fill: "#000" }}
                  />
                  <Tooltip formatter={(value, name) => [`${value} counts`, name]} />
                  <Legend verticalAlign="top" wrapperStyle={{ color: "#000" }} />
                  {(searchResults.top_species_names || []).map((species, i) => (
                    <Bar
                      key={species}
                      dataKey={species}
                      name={species}
                      fill={SPECIES_COLORS[i % SPECIES_COLORS.length]}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
              <p style={{ fontSize: 12, color: '#64748b', marginTop: 8 }}>
                Bar height = total individual birds counted across all birder reports. Top 5 species shown.
              </p>
            </div>
          )}

          {isSpeciesSearch && !searchResults?.is_generic_type && searchChartData.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h3>{`Where to Find ${searchResults?.searched_species} — Last 30 Days`}</h3>
              <ResponsiveContainer width="100%" height={Math.max(300, searchChartData.length * 40)}>
                <BarChart data={searchChartData} layout="vertical"
                  margin={{ top: 5, right: 30, left: 140, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    type="number"
                    tick={{ fill: "#000" }}
                    label={{ value: "Counts", position: "insideBottom", textAnchor: "middle", dy: 15, fill: "#000" }}
                  />
                  <YAxis type="category" dataKey="park" width={140} tick={{ fontSize: 12, fill: "#000" }} />
                  <Tooltip formatter={(value) => [`${value} counts`, 'Total']} />
                  <Bar dataKey="sighting_count" fill="#7c3aed" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {isSpecificPark && result.top_10_chart_data?.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h3>Top 10 Most Observed Species — Last 30 Days</h3>
              <ResponsiveContainer width="100%" height={350}>
                <BarChart data={result.top_10_chart_data} layout="vertical"
                  margin={{ top: 5, right: 50, left: 160, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="species" width={160} tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(value, name, props) => {
                    const reports = props?.payload?.report_count ?? 0;
                    return [`${value} birds counted across ${reports} birder reports`, 'Total'];
                  }} />
                  <Bar dataKey="total_counted" fill="#0ea5e9" label={{ position: 'right', fontSize: 12 }} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {isSpecificPark && (
            <div style={{ marginBottom: 24 }}>
              <h3>🔍 Rare & Notable Species to Watch For</h3>
              {result.rare_species_list?.length > 0 ? (
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                  {result.rare_species_list.map(r => (
                    <div key={r.name} style={{
                      background: 'white',
                      border: '1px solid #e2e8f0',
                      borderRadius: 12,
                      padding: '12px 16px',
                      minWidth: 160
                    }}>
                      <div style={{ fontWeight: 700, marginBottom: 4 }}>{r.name}</div>
                      <div style={{ fontSize: 12, color: '#64748b' }}>Last seen: {r.last_seen}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ color: '#64748b', fontSize: 14 }}>
                  No unusual species flagged in the last 30 days at this location.
                  All sightings appear to be commonly observed species.
                </p>
              )}
            </div>
          )}

          {isSpeciesList && result.species_chart_data?.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h3>Species Sighted — Last 30 Days</h3>
              <ResponsiveContainer width="100%" height={Math.max(300, result.species_chart_data.length * 24)}>
                <BarChart data={result.species_chart_data} layout="vertical"
                  margin={{ top: 5, right: 30, left: 140, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="species" width={140} tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#16a34a" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {(isFull || isSpeciesList) && result.species_highlights?.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h3 style={{ marginBottom: 12 }}>🦅 Species to Watch For</h3>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {result.species_highlights.map(s => (
                  <span key={s} style={{ padding: '4px 12px', background: '#dcfce7',
                    borderRadius: 20, fontSize: 13, color: '#166534' }}>{s}</span>
                ))}
              </div>
            </div>
          )}

          {isFull && result.chart_data?.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h3>Species Diversity by Park — Last 30 Days</h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={result.chart_data} layout="vertical"
                  margin={{ top: 5, right: 30, left: 120, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="park" width={120} tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Bar dataKey="species_count" fill="#0ea5e9" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {isFull && result.rankings?.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h3>Full Park Rankings</h3>
              <p style={{ margin: '0 0 12px', color: '#64748b', fontSize: 13, fontStyle: 'italic' }}>
                Rarity Score = Higher means more unusual sightings.
              </p>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ background: '#f1f5f9' }}>
                    <th style={{ padding: '8px 12px', textAlign: 'left' }}>Rank</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left' }}>Park</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left' }}>Species</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left' }}>Rarity Score</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rankings.map((r, i) => (
                    <tr key={r.park} style={{ borderBottom: '1px solid #e2e8f0' }}>
                      <td style={{ padding: '8px 12px' }}>#{i + 1}</td>
                      <td style={{ padding: '8px 12px' }}>{r.park}</td>
                      <td style={{ padding: '8px 12px' }}>{r.species_count}</td>
                      <td style={{ padding: '8px 12px' }}>{r.rarity_score?.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        );
      })()}

      <footer style={{ marginTop: 40, paddingTop: 16, borderTop: '1px solid #e2e8f0',
                       color: '#94a3b8', fontSize: 12, textAlign: 'center' }}>
        Data: eBird API + Open-Meteo Weather | Real-time NYC Birding Intelligence
      </footer>
    </div>
  );
}
