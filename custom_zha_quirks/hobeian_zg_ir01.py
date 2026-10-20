"""Custom ZHA quirk for the HOBEIAN ZG-IR01 Zigbee IR blaster (with temp/humidity).

Reuses the Zosung IR clusters from the upstream TS1201 quirk
(zhaquirks.tuya.ts1201), adds a signature for this model, and works around
the firmware always requesting IR send chunks with seq=0.
"""

from zigpy.profiles import zha
from zigpy.zcl.clusters.general import (
    Basic,
    Groups,
    Identify,
    OnOff,
    PowerConfiguration,
    Scenes,
)
from zigpy.zcl.clusters.measurement import RelativeHumidity, TemperatureMeasurement

from zhaquirks.const import (
    DEVICE_TYPE,
    ENDPOINTS,
    INPUT_CLUSTERS,
    MODELS_INFO,
    OUTPUT_CLUSTERS,
    PROFILE_ID,
)
from zhaquirks.tuya.ts1201 import ZosungIRBlaster, ZosungIRControl, ZosungIRTransmit

TUYA_MCU_CLUSTER = 0xEF00


class HobeianIRTransmit(ZosungIRTransmit):
    """ZG-IR01 transmit cluster.

    This firmware does not echo the sequence number it was given: it always
    requests chunks of the outgoing IR message with seq=0. Map such requests
    to the most recently queued message so the upstream logic can serve it.
    """

    def handle_cluster_request(self, hdr, args, *, dst_addressing=None):
        """Handle a cluster request."""
        pending = self.endpoint.device.ir_msg_to_send
        if hdr.command_id == self.ServerCommandDefs.receive_ir_frame_02.id and (
            args.seq == 0 or args.seq not in pending
        ):
            latest = next((s for s in reversed(pending) if s != args.seq), None)
            if latest is not None:
                pending[args.seq] = pending[latest]
        return super().handle_cluster_request(
            hdr, args, dst_addressing=dst_addressing
        )


class HobeianZGIR01(ZosungIRBlaster):
    """HOBEIAN ZG-IR01 IR blaster."""

    signature = {
        MODELS_INFO: [("HOBEIAN", "ZG-IR01")],
        ENDPOINTS: {
            1: {
                PROFILE_ID: zha.PROFILE_ID,
                DEVICE_TYPE: zha.DeviceType.ON_OFF_LIGHT,  # 0x0100
                INPUT_CLUSTERS: [
                    Basic.cluster_id,
                    PowerConfiguration.cluster_id,
                    Identify.cluster_id,
                    Groups.cluster_id,
                    Scenes.cluster_id,
                    OnOff.cluster_id,
                    TemperatureMeasurement.cluster_id,
                    RelativeHumidity.cluster_id,
                    ZosungIRControl.cluster_id,  # 0xE004
                    ZosungIRTransmit.cluster_id,  # 0xED00
                    TUYA_MCU_CLUSTER,
                ],
                OUTPUT_CLUSTERS: [Identify.cluster_id],
            },
        },
    }

    replacement = {
        ENDPOINTS: {
            1: {
                PROFILE_ID: zha.PROFILE_ID,
                DEVICE_TYPE: zha.DeviceType.ON_OFF_LIGHT,
                INPUT_CLUSTERS: [
                    Basic.cluster_id,
                    PowerConfiguration.cluster_id,
                    Identify.cluster_id,
                    Groups.cluster_id,
                    Scenes.cluster_id,
                    OnOff.cluster_id,
                    TemperatureMeasurement.cluster_id,
                    RelativeHumidity.cluster_id,
                    ZosungIRControl,
                    HobeianIRTransmit,
                    TUYA_MCU_CLUSTER,
                ],
                OUTPUT_CLUSTERS: [Identify.cluster_id],
            },
        },
    }
