import { UIAbility } from '@kit.AbilityKit';
import { window } from '@kit.ArkUI';
import { BusinessError } from '@kit.BasicServicesKit';
import { cs30Usb } from '../usb/Cs30Usb';

export default class EntryAbility extends UIAbility {
  onDestroy(): void {
    cs30Usb.shutdown().catch(() => { console.error('释放相机失败'); });
  }
  onWindowStageCreate(windowStage: window.WindowStage): void {
    try {
      windowStage.loadContent('pages/Index', (err: BusinessError) => {
        if (err.code) {
          console.error(`load content failed ${err.code}`);
        }
      });
    } catch (e) {
      console.error('load content failed');
    }
  }
}
