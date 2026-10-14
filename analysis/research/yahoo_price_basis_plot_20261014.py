"""Standalone research plot; requires matplotlib, never accesses production data."""
from pathlib import Path
import pandas as pd,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    out=Path(__file__).resolve().parents[2]/'outputs/yahoo_price_basis_comparison_20261014'
    c=pd.read_csv(out/'classifications.csv');d=pd.read_csv(out/'dow.csv');order=pd.read_csv(out/'coverage.csv').ticker.tolist()
    features=['EMA20','SMA50','SMA200','RSI14_30','RSI14_70','High20','GapAbove2pct']
    a=c.assign(percent=lambda z:100*z.classification_differences/z.n).pivot(index='ticker',columns='feature',values='percent').reindex(index=order,columns=features)
    a['Dow labels']=d.set_index('ticker').reindex(order).eval('100*pivot_label_mismatches/common_pivots').to_numpy()
    fig,ax=plt.subplots(figsize=(11,12));im=ax.imshow(a.to_numpy(),aspect='auto',cmap='YlOrRd',vmin=0)
    ax.set_xticks(range(len(a.columns)),a.columns,rotation=35,ha='right');ax.set_yticks(range(len(a)),a.index)
    for i in range(len(a)):
     for j in range(len(a.columns)):
      v=a.iloc[i,j];ax.text(j,i,f'{v:.1f}' if np.isfinite(v) else '—',ha='center',va='center',fontsize=8,color='black')
    ax.set_title('False vs reconstructed True: classification differences (%)\nMatched, qualified sessions; research diagnostics, not strategy signals')
    fig.colorbar(im,ax=ax,label='Different classification (%)',shrink=.6);fig.tight_layout();fig.savefig(out/'classification_impact.png',dpi=150);plt.close(fig)


if __name__ == "__main__":
    main()
