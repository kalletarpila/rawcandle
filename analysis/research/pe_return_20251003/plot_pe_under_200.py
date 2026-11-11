"""Render a separate P/E <= 200 view from existing unrounded research values."""

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from revised_analysis import relationship


def main():
    output = Path(__file__).resolve().parent/'revised_outputs'
    audit = json.loads((output/'validation.json').read_text())
    valid = [r for r in audit['audit'] if r['exclusion'] is None]
    rows = [{'ticker':r['ticker'], 'pe':r['pe'], 'return':r['return_12m_pct']}
            for r in valid if r['pe'] <= 200]
    assert len(rows) == 116 and all(0 < r['pe'] <= 200 for r in rows)
    fit = relationship(rows)
    x = np.array([r['pe'] for r in rows])
    y = np.array([r['return'] for r in rows])
    fig, ax = plt.subplots(figsize=(10,6))
    ax.scatter(x,y,s=24,color='#216e80',alpha=.75,label=f'Stocks (N={len(rows)})')
    line = np.array([x.min(),x.max()])
    ax.plot(line,fit['alpha']+fit['beta']*line,color='#ad2947',label='OLS (P/E <= 200)')
    ax.axhline(0,color='#555555',linewidth=.8)
    ax.set(xlabel='pe_2025_10_03',ylabel='return_12m_pct',xlim=(0,200))
    ax.set_title('Annualized quarterly P/E vs subsequent 12-month return',fontsize=13)
    ax.grid(alpha=.2)
    ax.legend()
    highest = max(rows,key=lambda r:r['return'])
    ax.annotate(highest['ticker'],(highest['pe'],highest['return']),xytext=(10,-4),
                textcoords='offset points',fontsize=9)
    fig.text(.08,.02,'P/E = 2025-10-03 Close / (latest published quarter revised diluted EPS x 4)\n'
             'Return = 2025-10-03 to 2026-10-02; revised historical EPS, not original PIT.\n'
             'Only P/E <= 200 included; regression refitted on 116 observations.',fontsize=9)
    fig.tight_layout(rect=(0,.12,1,1))
    path = output/'scatter_pe_le_200.png'
    fig.savefig(path,dpi=160)
    plt.close(fig)
    print(json.dumps({'plot':str(path),'excluded':len(valid)-len(rows),**fit},indent=2))


if __name__ == '__main__':
    main()
