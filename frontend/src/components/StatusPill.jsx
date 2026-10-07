const TEXT = {
  reliable: 'Reliable',
  volatile: 'Volatile',
  unreliable: 'Unreliable',
}

export default function StatusPill({ status }) {
  if (!status) return null
  return (
    <span className={`pill ${status}`}>
      <i aria-hidden="true" />
      {TEXT[status] ?? status}
    </span>
  )
}

export const STATUS_HELP = {
  reliable: 'Low model uncertainty and normal volatility. The forecast can be planned against.',
  volatile: 'The model knows this series, but demand itself swings a lot. Keep a buffer.',
  unreliable: 'Epistemic uncertainty is high: the model is outside what it has learned. Check the source before using this number.',
}
