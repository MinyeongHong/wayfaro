# 프론트엔드 읽기 안내

텍스트 CV/JD를 비공개로 비교하는 단일 화면입니다. Node.js 22를 사용합니다.

## 설치와 검증

```sh
npm ci
npm test
npm run typecheck
npm run build
npm run dev
```

Tailwind v4용 `tailwindcss`, `@tailwindcss/vite` 4.1.18을 사용하도록 설정했습니다.
해당 plugin은 기존 Vite 5를 지원합니다. UI·상태 관리 라이브러리는 추가하지 않았습니다.

Mac에서 의존성을 설치한 뒤 `package.json`, `package-lock.json`, 설치 버전의 일치를
확인했습니다. Node.js 22에서 테스트 33개, TypeScript 검사와 프로덕션 빌드가 통과했습니다.
`package.json`과 `package-lock.json`은 함께 커밋합니다. 새 환경에서는 `npm ci`로 설치합니다.
실제 브라우저의 외형·키보드·dialog focus 동작은 아래 안내에 따라 별도로 확인합니다.

## 화면에서 시작해 데이터 흐름 따라가기

1. `src/App.tsx`: 공통 배치와 브라우저 lifecycle. Controller 인스턴스 하나를 소유합니다.
2. `src/pages/AnalysisPage.tsx`: Controller를 구독하고 화면을 조립합니다.
3. `src/components/analysis/AnalysisForm.tsx`: 입력·동의·제출 UI를 조립합니다.
4. `DocumentInput.tsx`, `ConsentPanel.tsx`: 값과 callback을 받는 입력·동의 컴포넌트입니다.
5. `AnalysisStatus.tsx`: 대기·재시도·오류·삭제 상태를 표시합니다.
6. `AnalysisResults.tsx`, `RequirementCard.tsx`, `EvidenceList.tsx`: 근거 중심 결과입니다.
7. `DeleteAnalysisDialog.tsx`: native modal을 열고 취소 버튼 focus와 이전 focus를 관리합니다.
8. `src/analysisController.ts`: 애플리케이션 상태, 요청 취소, polling, 제출·삭제입니다.
9. `src/analysisApi.ts`, `analysisTypes.ts`, `analysisText.ts`: HTTP·보안·계약·입력 및 근거 검증입니다.

Flutter에 대응하면 AnalysisPage는 Screen, 작은 컴포넌트는 Widget입니다.
props는 생성자 인자, callback은 사용자 행동을 부모에 알리는 함수입니다.
`useState`는 작은 UI 상태를 보관합니다. Controller는 ChangeNotifier와 유사한 역할이며,
`useSyncExternalStore`가 Controller의 변경을 React에 연결합니다.
폼이나 하위 컴포넌트에서 Controller를 새로 만들지 않습니다.

```tsx
<DocumentInput
  value={state.cv}
  onChange={value => onTextChange('cv', value)}
  // 나머지 표시용 props는 생략했습니다.
/>
```

상태는 props로 내려가고 이벤트는 callback으로 올라갑니다.
표시 컴포넌트가 직접 fetch하거나 polling을 시작하거나 POST 재전송을 결정하지 않습니다.

## 스타일 구조

`vite.config.ts`가 Tailwind를 등록합니다. `src/style.css`에는 다음만 남깁니다.

- `@theme`: 기존 색상과 제목용 폰트.
- `max-mobile`: 기존과 동일하게 680px 이하인 모바일 조건.
- `@layer base`: 기본 글꼴·제목·focus outline·checkbox·근거 인용 스타일.
- 반복 패턴 4개: `page-width`, `eyebrow`, `notice`, `session-note`.

나머지 배치·스타일은 해당 JSX의 utility class로 확인합니다.
Button의 variant는 Tailwind가 찾을 수 있는 완성된 class 문자열입니다.
`components/ui/Button.tsx`는 native props와 ref를 전달하며 기본 type은 `button`입니다.
폼 제출에는 명시적으로 `type="submit"`을 지정합니다.

native `<dialog>`를 유지합니다. Node 기반 렌더링 테스트로 label·disabled·markup을
검사할 수 있지만, 실제 focus trap·Escape·backdrop·반응형 외형을 입증하지는 못합니다.

## 개인정보와 브라우저 검증

문서·결과·분석 식별자를 브라우저 저장소, analytics, 로그, URL 상태에 넣지 않습니다.
제출 당시 원문 snapshot과 Unicode code-point 근거 검증을 유지합니다.
응답이 유실된 POST를 자동 재전송하지 않습니다. 동의·쿠키·CSRF·요청 취소·서버 삭제와
페이지 이탈 시 메모리 정리도 유지합니다.

브라우저 검증에는 합성 문서와 mock/test backend를 사용합니다.
스타일 확인을 위해 실제 Gemini 분석을 실행하지 않습니다.
키보드 탐색, dialog 취소와 focus 복원, 긴 인용문, disabled 상태 및 680px 전후를 확인합니다.
