import { createRoot } from 'react-dom/client';
import App from './app/App';
import './style.css';
import openSeadragonUrl from '../../5_PG_Develop/viewer_component/openseadragon.min.js?url';

declare global {
  interface Window {
    OpenSeadragon: (options: Record<string, unknown>) => any;
  }
}

const root = createRoot(document.getElementById('root')!);
const viewerScript = document.createElement('script');
viewerScript.src = openSeadragonUrl;
viewerScript.onload = () => root.render(<App />);
viewerScript.onerror = () => {
  root.render(<main className="load-error">影像檢視元件載入失敗。請重新建置本機資產。</main>);
};
document.head.appendChild(viewerScript);
