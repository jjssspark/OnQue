export type Metric = {
  label: string;
  value: number;
  hint: string;
  /** 주의가 필요한 수치(지연 등)를 경고색으로 표시한다. */
  alert?: boolean;
};
