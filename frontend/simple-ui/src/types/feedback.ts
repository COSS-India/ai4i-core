/** Implicit feedback action types sent to the feedback service. */
export type ImplicitAction =
  | 'COPY_TRANSLATION'
  | 'COPY_SOURCE'
  | 'CLEAR_RESULTS'
  | 'RETRANSLATE'
  | 'CORRECTION'
  | 'ABANDON';
