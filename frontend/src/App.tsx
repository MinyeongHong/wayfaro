import { useEffect, useState } from 'react';
import { AnalysisController } from './analysisController';
import { AnalysisPage } from './AnalysisPage';

export function App() {
  const [controller] = useState(() => new AnalysisController());
  useEffect(() => {
    const onHide = () => { controller.pause(); controller.forget(); };
    const onShow = () => { controller.activate(); };
    const beforeUnload = (event: BeforeUnloadEvent) => {
      const state = controller.getSnapshot();
      if (state.cv || state.jd || state.accepted) { event.preventDefault(); event.returnValue = ''; }
    };
    window.addEventListener('pagehide', onHide);
    window.addEventListener('pageshow', onShow); window.addEventListener('beforeunload', beforeUnload);
    return () => {
      window.removeEventListener('pagehide', onHide);
      window.removeEventListener('pageshow', onShow); window.removeEventListener('beforeunload', beforeUnload);
      controller.pause(); controller.forget();
    };
  }, [controller]);
  return <>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <div className="site-header"><a className="wordmark" href="#main-content">wayfaro<span aria-hidden="true">.</span></a><span className="small">Private CV comparison</span></div>
    <main id="main-content"><AnalysisPage controller={controller} /></main>
    <footer className="site-footer"><span>Wayfaro</span><p>Compare your experience with evidence. Your documents stay private.</p><span className="small">Career fit and work eligibility are separate.</span></footer>
  </>;
}
