import { useState } from 'react';

type State = 'idle' | 'loading' | 'success' | 'error';

export default function DeleteForm() {
  const [email, setEmail] = useState('');
  const [state, setState] = useState<State>('idle');
  const [errorMsg, setErrorMsg] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setState('loading');
    try {
      const res = await fetch('/delete-request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (data.ok) {
        setState('success');
      } else {
        setErrorMsg(data.error || 'Tuntematon virhe.');
        setState('error');
      }
    } catch {
      setErrorMsg('Verkkovirhe. Yritä uudelleen.');
      setState('error');
    }
  }

  if (state === 'success') {
    return (
      <div style={{ background: '#f0fff4', border: '1px solid #86efac', borderRadius: 8, padding: '16px 20px', maxWidth: 480 }}>
        <strong>Sähköposti lähetetty!</strong>
        <p style={{ margin: '8px 0 0', color: '#555', fontSize: 15 }}>
          Lähetimme viestin osoitteeseen <strong>{email}</strong>.
          Jos tiedot löytyvät palvelimelta, viesti sisältää vahvistuslinkin. Linkki on voimassa 24 tuntia.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} style={{ maxWidth: 480 }}>
      {state === 'error' && (
        <div style={{ background: 'var(--torium-red-subtle)', border: '1px solid #fca5a5', borderRadius: 8, padding: '12px 16px', marginBottom: 16, fontSize: 14, color: '#900' }}>
          {errorMsg}
        </div>
      )}
      <label style={{ display: 'block', fontWeight: 500, marginBottom: 6, fontSize: 15 }}>
        Sähköpostiosoite
      </label>
      <input
        type="email"
        required
        value={email}
        onChange={e => setEmail(e.target.value)}
        placeholder="sinä@esimerkki.fi"
        style={{
          width: '100%', padding: '10px 14px',
          border: '1px solid #ddd', borderRadius: 6,
          fontSize: 15, fontFamily: 'inherit',
          marginBottom: 16, boxSizing: 'border-box',
        }}
      />
      <button
        type="submit"
        disabled={state === 'loading'}
        style={{
          background: 'var(--torium-red)', color: '#fff',
          border: 'none', padding: '10px 24px',
          borderRadius: 6, fontSize: 15, fontWeight: 500,
          cursor: state === 'loading' ? 'not-allowed' : 'pointer',
          opacity: state === 'loading' ? 0.7 : 1,
          fontFamily: 'inherit',
        }}
      >
        {state === 'loading' ? 'Lähetetään…' : 'Lähetä vahvistuslinkki'}
      </button>
    </form>
  );
}
