import { useEffect, useState } from 'react';
import { AnalysisController } from './analysisController';
import { AnalysisPage } from './pages/AnalysisPage';

export function App() {
  const [controller] = useState(() => new AnalysisController());

  useEffect(() => {
    const onHide = () => {
      controller.pause();
      controller.forget();
    };
    const onShow = () => controller.activate();
    const beforeUnload = (event: BeforeUnloadEvent) => {
      const state = controller.getSnapshot();
      if (state.cv || state.jd || state.accepted) {
        event.preventDefault();
        event.returnValue = '';
      }
    };

    window.addEventListener('pagehide', onHide);
    window.addEventListener('pageshow', onShow);
    window.addEventListener('beforeunload', beforeUnload);
    return () => {
      window.removeEventListener('pagehide', onHide);
      window.removeEventListener('pageshow', onShow);
      window.removeEventListener('beforeunload', beforeUnload);
      controller.pause();
      controller.forget();
    };
  }, [controller]);

  return (
    <>
      <a
        className="absolute -top-20 left-4 z-5 bg-white p-3 focus:top-3"
        href="#main-content"
      >
        Skip to content
      </a>
      <div className="page-width flex items-center justify-between gap-5 border-b border-[#dcded6] py-6 max-mobile:flex-wrap max-mobile:py-[18px]">
        <a className="text-[28px] font-[750] tracking-[-.06em] text-[#243b30] no-underline" href="#main-content">
          wayfaro<span className="text-[#a17435]" aria-hidden="true">.</span>
        </a>
        <span className="text-[13px]">Private CV comparison</span>
      </div>
      <main id="main-content" className="page-width min-h-[65vh]">
        <AnalysisPage controller={controller} />
      </main>
      <footer className="page-width mt-16 flex flex-wrap items-center justify-between gap-5 border-t border-[#dcded6] py-7 text-xs text-[#667267] max-mobile:mt-[45px] max-mobile:gap-2.5">
        <span>Wayfaro</span>
        <p className="m-0 max-w-[390px]">
          Compare your experience with evidence. Your documents stay private.
        </p>
        <span className="text-[13px]">Career fit and work eligibility are separate.</span>
      </footer>
    </>
  );
}
