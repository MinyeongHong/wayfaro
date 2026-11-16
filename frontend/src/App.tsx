import { useEffect, useRef, useState } from 'react';
import { AnalysisController } from './analysisController';
import { AnalysisPage } from './AnalysisPage';
import { DiscoveryPage } from './DiscoveryPage';

function currentView() {
  const params = new URLSearchParams(window.location.search);
  if (params.get('view') === 'analysis') return 'analysis';
  if (params.get('view') === 'discover' || ['q', 'location', 'country_text', 'region_text', 'origin', 'source_id', 'remote_mention', 'sort', 'page', 'page_size', 'job'].some(key => params.has(key))) return 'discover';
  return 'analysis';
}
export function App() {
  const [view, setView] = useState(currentView);
  const [controller] = useState(() => new AnalysisController());
  const discoveryUrl = useRef('?view=discover');
  useEffect(() => {
    const onPop = () => { if (currentView() === 'discover') discoveryUrl.current = window.location.search; setView(currentView()); };
    const onHide = () => { controller.pause(); controller.forget(); };
    const onShow = () => { if (currentView() === 'analysis') controller.activate(); };
    const beforeUnload = (event: BeforeUnloadEvent) => {
      const state = controller.getSnapshot();
      if (state.cv || state.jd || state.accepted) { event.preventDefault(); event.returnValue = ''; }
    };
    window.addEventListener('popstate', onPop); window.addEventListener('pagehide', onHide);
    window.addEventListener('pageshow', onShow); window.addEventListener('beforeunload', beforeUnload);
    return () => {
      window.removeEventListener('popstate', onPop); window.removeEventListener('pagehide', onHide);
      window.removeEventListener('pageshow', onShow); window.removeEventListener('beforeunload', beforeUnload);
      controller.pause(); controller.forget();
    };
  }, [controller]);
  function navigate(next: 'analysis' | 'discover') {
    if (view === 'discover') discoveryUrl.current = window.location.search;
    window.history.pushState(null, '', `${window.location.pathname}${next === 'discover' ? discoveryUrl.current : '?view=analysis'}`);
    setView(next);
  }
  return <>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <div className="site-header"><a className="wordmark" href="?view=analysis" onClick={event => { event.preventDefault(); navigate('analysis'); }}>wayfaro<span aria-hidden="true">.</span></a>
      <nav aria-label="Main navigation"><button aria-current={view === 'analysis' ? 'page' : undefined} onClick={() => navigate('analysis')}>CV comparison</button><button aria-current={view === 'discover' ? 'page' : undefined} onClick={() => navigate('discover')}>Job discovery</button></nav>
    </div>
    <main id="main-content">{view === 'analysis' ? <AnalysisPage controller={controller} /> : <DiscoveryPage />}</main>
    <footer className="site-footer"><span>Wayfaro</span><p>Discover opportunities beyond borders. Make your next step with evidence.</p><span className="small">Career fit and work eligibility are separate.</span></footer>
  </>;
}
